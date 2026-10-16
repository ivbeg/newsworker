#!/usr/bin/env python
"""High-level, concurrent-safe feed extraction service."""

from __future__ import annotations

import concurrent.futures
import logging
import time
from typing import Any, Dict, Iterable, Optional, Tuple

from .bridges import default_bridge_dirs, load_bridges, select_bridge
from .cache import ContentCache, SpecCache, key_for
from .diagnostics import ExtractionDiagnostics
from .enrich import enrich_feed, extract_fulltext_with_kind
from .extractor import FeedExtractor
from .fetch import policy_from_settings
from .plugins import load_plugins, select_plugin
from .runtime import ExtractionContext, SingleFlight, closing_context
from .settings import Settings
from .sources import DocumentSource
from .spec import FeedSpec, SpecAnalyzer, SpecExtractor
from .tools import (
    assign_item_identities,
    decode_html,
    find_next_link,
    resolve_feed_language,
    sanitize_feed_links,
)

log = logging.getLogger(__name__)


class FeedService:
    """Build feeds while isolating each request and reusing safe resources."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        use_cache: bool = True,
        plugins: Optional[list] = None,
        bridges: Optional[list] = None,
        *,
        extensions_loaded: bool = False,
        clock=None,
    ):
        """``clock`` (a callable returning an aware datetime) resolves relative
        dates such as "2 hours ago"; it defaults to the current time."""
        self.settings = settings or Settings()
        self.clock = clock
        self.settings.validate()
        self.use_cache = use_cache
        self.plugins = list(plugins or []) if extensions_loaded else load_plugins(extra=plugins)
        if bridges is not None:
            self.bridges = list(bridges)
        else:
            self.bridges = load_bridges(*default_bridge_dirs(self.settings))
        cache_dir = self.settings.resolved_cache_dir()
        self.content_cache = ContentCache(
            cache_dir,
            ttl=self.settings.content_ttl,
            max_entries=self.settings.content_cache_max_entries,
            max_bytes=self.settings.content_cache_max_bytes,
        )
        self.spec_cache = SpecCache(
            cache_dir,
            ttl=self.settings.spec_ttl,
            max_entries=self.settings.spec_cache_max_entries,
        )
        self.extractor = FeedExtractor(
            filtered_text_length=self.settings.filtered_text_length,
            max_bytes=self.settings.max_content_bytes,
            verify_tls=self.settings.verify_tls,
            respect_robots=self.settings.respect_robots,
            timeout=self.settings.request_timeout,
            proxy=self.settings.proxy,
            extra_headers=self.settings.extra_headers,
            cookies_file=self.settings.cookies_file,
            default_language=self.settings.default_language,
        )
        self.extractor.default_timezone = self.settings.default_timezone
        self.extractor.base_policy = policy_from_settings(self.settings)
        self.extractor.redirect_limit = self.settings.redirect_limit
        self.extractor.allowed_hosts = tuple(self.settings.allowed_hosts)
        self.extractor.block_private_hosts = self.settings.block_private_hosts
        self.extractor.allow_private_hosts = self.settings.allow_private_hosts
        self.extractor.trusted_proxy = self.settings.trusted_proxy
        self._content_flights = SingleFlight()
        self._spec_flights = SingleFlight()
        self._renderer = None

    def new_context(self, *, source: str = "network", base_url: Optional[str] = None):
        diagnostics = ExtractionDiagnostics(source=source, requested_url=base_url)
        context = ExtractionContext(
            source=source,
            base_url=base_url,
            default_timezone=self.settings.default_timezone,
            diagnostics=diagnostics,
        )
        if self.clock is not None:
            context.clock = self.clock
        return context

    def _fetch(
        self,
        url: str,
        force_refresh: bool = False,
        *,
        revalidate: bool = False,
        context: Optional[ExtractionContext] = None,
    ) -> bytes:
        """Return bytes, optionally contacting upstream even while cache is fresh."""
        context = context or self.new_context(base_url=url)

        def populate() -> Tuple[bytes, Dict[str, Any]]:
            stale, meta = self.content_cache.get_generation(url, fresh_only=False)
            if self.use_cache and not force_refresh and not revalidate:
                fresh, fresh_meta = self.content_cache.get_generation(url, fresh_only=True)
                if fresh is not None:
                    log.debug("Content cache hit for %s", url)
                    return fresh, fresh_meta
            conditional = meta if self.use_cache and stale is not None and meta else None
            if force_refresh:
                conditional = None
            with self.extractor.activate_context(context):
                data = self.extractor.fetch(
                    url,
                    self.settings.user_agent,
                    conditional=conditional,
                )
            response_meta = dict(context.response_meta)
            if data is None:
                if stale is None:
                    raise RuntimeError("upstream returned 304 without a cached body")
                self.content_cache.touch(url)
                fresh_validators = {
                    key: response_meta.get(key) for key in ("etag", "last_modified")
                }
                if self.use_cache:
                    self.content_cache.update_meta(url, fresh_validators)
                merged = dict(meta)
                merged.update(response_meta)
                merged.update({k: v for k, v in fresh_validators.items() if v})
                merged["cache_state"] = "revalidated"
                return stale, merged
            response_meta["cache_state"] = "miss" if stale is None else "changed"
            if self.use_cache:
                self._store_content(url, data, response_meta)
            return data, response_meta

        data, response_meta = self._content_flights.call(key_for(url), populate)
        context.response_meta = dict(response_meta)
        context.content_language = context.content_language or _header_language(response_meta)
        diagnostics = context.diagnostics
        if diagnostics is not None:
            diagnostics.effective_url = response_meta.get("effective_url") or url
            diagnostics.metadata.update(
                {
                    "status": response_meta.get("status"),
                    "cache_state": response_meta.get("cache_state", "hit"),
                }
            )
        return data

    def _store_content(self, url: str, data: bytes, meta: MappingLike = None) -> None:
        try:
            self.content_cache.set(url, data, meta=dict(meta or {}))
        except OSError as exc:
            log.warning("Failed to cache content for %s: %s", url, exc)

    def _spec_cache_enabled(self, context: ExtractionContext) -> bool:
        # A local file or stdin document must not read or overwrite the spec
        # inferred for the live site at the same base URL.
        return self.use_cache and context.source not in {"file", "stdin"}

    def _get_or_build_spec(
        self, url: str, data: bytes, context: ExtractionContext, *, rebuild: bool = False
    ) -> Optional[FeedSpec]:
        use_cache = self._spec_cache_enabled(context)
        if use_cache and not rebuild:
            spec = self.spec_cache.get(url)
            if spec is not None:
                if context.diagnostics:
                    context.diagnostics.add_attempt("cached_spec", "selected")
                return spec

        def build():
            if use_cache and not rebuild:
                cached = self.spec_cache.get(url)
                if cached is not None:
                    return cached
            analyzer = SpecAnalyzer(extractor=self.extractor)
            spec = analyzer.analyze(url, data=data, user_agent=self.settings.user_agent)
            if use_cache and spec is not None and spec.fields:
                try:
                    self.spec_cache.set(url, spec)
                except OSError as exc:
                    log.warning("Failed to cache spec for %s: %s", url, exc)
            return spec

        flight_key = ("rebuild:" if rebuild else "") + key_for(url)
        return self._spec_flights.call(flight_key, build)

    def get_feed(
        self,
        url: str,
        force_refresh: bool = False,
        explicit_spec: Optional[FeedSpec] = None,
        max_pages: int = 1,
        data: Optional[bytes] = None,
        *,
        context: Optional[ExtractionContext] = None,
        revalidate: bool = False,
        render: Optional[bool] = None,
    ) -> dict:
        context = context or self.new_context(
            source="network" if data is None else "prefetched", base_url=url
        )
        diagnostics = context.diagnostics
        if diagnostics:
            diagnostics.start("total")
        with self.extractor.activate_context(context), closing_context(context):
            if render is True or (render is None and self.settings.render):
                data = self._render(url, context)
            if data is None:
                data = self._fetch(
                    url,
                    force_refresh=force_refresh,
                    revalidate=revalidate,
                    context=context,
                )
            extraction_url = context.response_meta.get("effective_url") or url
            feed = self._extract(
                extraction_url,
                data,
                explicit_spec=explicit_spec,
                context=context,
            )
            if max_pages and max_pages > 1:
                self._follow_pagination(
                    extraction_url,
                    data,
                    explicit_spec,
                    feed,
                    max_pages,
                    context=context,
                    revalidate=revalidate,
                )
            if getattr(self.settings, "structured_data", True):
                feed = self._apply_structured_data(feed, data, extraction_url, context)
            if not feed.get("items") and self.settings.undated_fallback:
                feed = self._extract_undated(data, extraction_url, context)
            if (
                not feed.get("items")
                and self.settings.render_fallback
                and not context.metadata_get("rendered", False)
                and _looks_client_rendered(data)
            ):
                try:
                    rendered = self._render(url, context)
                except Exception as exc:
                    if diagnostics:
                        diagnostics.warnings.append(
                            f"Browser fallback failed: {type(exc).__name__}"
                        )
                else:
                    extraction_url = context.response_meta.get("effective_url") or extraction_url
                    feed = self._extract(extraction_url, rendered, context=context)
            sanitize_feed_links(feed, fallback_url=extraction_url)
            assign_item_identities(feed.get("items", []), page_url=extraction_url)
            enrich_feed(feed)
            if self.settings.full_text:
                self._add_full_text(feed, context)
            provenance = feed.setdefault("provenance", {})
            provenance["source"] = context.source
            if diagnostics:
                diagnostics.score(feed)
                diagnostics.stop("total")
                # Only content-derived facts belong in the feed itself, so an
                # unchanged page renders to identical bytes (stable ETags).
                # Timings and cache state stay in the diagnostics object.
                provenance.update(
                    {
                        "strategy": diagnostics.chosen_strategy,
                        "confidence": diagnostics.confidence,
                        "warnings": list(diagnostics.warnings),
                        "effective_url": diagnostics.effective_url or extraction_url,
                    }
                )
            return feed

    def _extract(
        self,
        url: str,
        data: bytes,
        *,
        explicit_spec: Optional[FeedSpec] = None,
        context: ExtractionContext,
    ) -> dict:
        diagnostics = context.diagnostics
        plugin = select_plugin(url, self.plugins)
        if plugin is not None:
            started = time.monotonic()
            feed = plugin.extract(url, data=data, user_agent=self.settings.user_agent)
            if diagnostics:
                diagnostics.chosen_strategy = "plugin"
                diagnostics.add_attempt(
                    "plugin",
                    "success",
                    item_count=len(feed.get("items", [])),
                    elapsed_ms=(time.monotonic() - started) * 1000,
                )
            return feed

        spec = explicit_spec
        strategy = "explicit_spec" if spec is not None else None
        if spec is None:
            bridge_spec = select_bridge(url, self.bridges)
            if bridge_spec is not None:
                spec, strategy = bridge_spec, "bridge"
            else:
                spec, strategy = self._get_or_build_spec(url, data, context), "spec"
        started = time.monotonic()
        if spec is not None and spec.fields:
            feed = self._apply_spec(url, data, spec, strategy or "spec", started, context)
            if feed.get("items") or strategy != "spec":
                # Explicit specs and bridges express user intent: an empty
                # result is reported, not silently replaced.
                return feed
            # An automatically inferred spec matched nothing; the layout most
            # likely changed. Re-analyse once and keep the new spec only if it works.
            if diagnostics:
                diagnostics.warnings.append("Cached spec matched no items; re-analysing the page")
            rebuilt = self._get_or_build_spec(url, data, context, rebuild=True)
            if rebuilt is not None and rebuilt.fields:
                feed = self._apply_spec(
                    url, data, rebuilt, "rebuilt_spec", time.monotonic(), context
                )
                if feed.get("items"):
                    return feed
            elif self._spec_cache_enabled(context):
                self.spec_cache.discard(url)
            started = time.monotonic()
        feed, _session = self.extractor.get_feed(
            url,
            data=data,
            user_agent=self.settings.user_agent,
            context=context,
        )
        if diagnostics:
            diagnostics.add_attempt(
                "dynamic",
                "success" if feed.get("items") else "empty",
                item_count=len(feed.get("items", [])),
                elapsed_ms=(time.monotonic() - started) * 1000,
            )
            diagnostics.chosen_strategy = "dynamic"
        return feed

    def _apply_spec(self, url, data, spec, strategy, started, context):
        feed = SpecExtractor(extractor=self.extractor).extract(
            url, spec, data=data, user_agent=self.settings.user_agent
        )
        diagnostics = context.diagnostics
        if diagnostics:
            diagnostics.add_attempt(
                strategy,
                "success" if feed.get("items") else "empty",
                item_count=len(feed.get("items", [])),
                elapsed_ms=(time.monotonic() - started) * 1000,
                selectors={"items": spec.items.selector},
            )
            diagnostics.chosen_strategy = strategy
        return feed

    def _apply_structured_data(self, feed, data, url, context):
        """Use JSON-LD/microdata items when heuristics found none; else sharpen dates."""
        from lxml import etree
        from lxml.html import fromstring

        from .structured import extract_structured_items, merge_structured_dates

        try:
            document = fromstring(decode_html(data), parser=etree.HTMLParser())
        except (ValueError, etree.ParserError, etree.XMLSyntaxError):
            return feed
        structured = extract_structured_items(
            document, url, default_timezone=self.settings.default_timezone
        )
        if not structured:
            return feed
        diagnostics = context.diagnostics
        if feed.get("items"):
            changed = merge_structured_dates(feed["items"], structured)
            if diagnostics and changed:
                diagnostics.metadata["structured_dates"] = changed
            return feed
        dated = [item for item in structured if item.get("pubdate") is not None]
        if len(dated) < 2:
            return feed
        if diagnostics:
            diagnostics.add_attempt("structured", "success", item_count=len(dated))
            diagnostics.chosen_strategy = "structured"
        title_nodes = document.xpath("//head/title")
        title = "".join(title_nodes[0].itertext()).strip() if title_nodes else feed.get("title")
        return {
            **feed,
            "title": title or feed.get("title") or url,
            "description": feed.get("description") or title or url,
            "language": self.settings.default_language
            or resolve_feed_language(
                document=document,
                content_language=context.content_language,
                text_samples=[item["title"] for item in dated],
            ),
            "items": [
                {
                    **item,
                    "unique_id": item["link"],
                    "extra": {
                        "links": [item["link"]],
                        "images": [item["image"]] if item.get("image") else [],
                    },
                }
                for item in dated
            ],
        }

    def _extract_undated(self, data: bytes, url: str, context: ExtractionContext) -> dict:
        from .undated import extract_undated_listing

        started = time.monotonic()
        feed, details = extract_undated_listing(
            data,
            url,
            min_items=self.settings.undated_min_items,
            min_confidence=self.settings.undated_min_confidence,
            language=self.settings.default_language or None,
            content_language=context.content_language,
        )
        if context.diagnostics:
            context.diagnostics.add_attempt(
                "undated",
                "success" if feed.get("items") else "rejected",
                item_count=len(feed.get("items", [])),
                elapsed_ms=(time.monotonic() - started) * 1000,
            )
            if feed.get("items"):
                context.diagnostics.chosen_strategy = "undated"
                context.diagnostics.metadata["undated"] = details
        return feed

    def _render(self, url: str, context: ExtractionContext) -> bytes:
        from .jsrender import PlaywrightRenderer

        if self._renderer is None:
            self._renderer = PlaywrightRenderer(
                policy_from_settings(self.settings),
                timeout=self.settings.render_timeout,
                max_bytes=self.settings.render_max_bytes,
                concurrency=self.settings.render_concurrency,
            )
        result = self._renderer.render(url)
        context.response_meta.update({"effective_url": result.effective_url, "rendered": True})
        if context.diagnostics:
            context.diagnostics.metadata["rendered"] = True
            context.diagnostics.add_attempt("browser", "rendered", elapsed_ms=result.elapsed_ms)
        return result.body

    def _follow_pagination(
        self,
        url: str,
        data: bytes,
        spec: Optional[FeedSpec],
        feed: dict,
        max_pages: int,
        *,
        context: ExtractionContext,
        revalidate: bool = False,
    ) -> None:
        from lxml import etree
        from lxml.html import fromstring

        visited = {url}
        current_url, current_data = url, data
        pages = 1
        while pages < max_pages:
            try:
                doc = fromstring(
                    decode_html(current_data),
                    parser=etree.HTMLParser(remove_blank_text=True),
                )
            except Exception:
                break
            next_url = find_next_link(doc, current_url)
            if not next_url or next_url in visited:
                break
            visited.add(next_url)
            try:
                next_data = self._fetch(next_url, revalidate=revalidate, context=context)
            except Exception as exc:
                log.warning("Pagination stopped at %s: %s", next_url, exc)
                if context.diagnostics:
                    context.diagnostics.warnings.append(
                        f"Pagination stopped after {pages} page(s): {type(exc).__name__}"
                    )
                break
            # Listing pages share one layout: reuse the first page's spec rather
            # than analysing and caching one spec per ?page=N URL.
            page_spec = spec or (
                self.spec_cache.get(url) if self._spec_cache_enabled(context) else None
            )
            page_feed = self._extract(next_url, next_data, explicit_spec=page_spec, context=context)
            items = feed.setdefault("items", [])
            known = {item.get("link") or item.get("unique_id") for item in items}
            for item in page_feed.get("items", []):
                identity = item.get("link") or item.get("unique_id")
                if identity not in known:
                    known.add(identity)
                    items.append(item)
            current_url, current_data = next_url, next_data
            pages += 1

    def _add_full_text(self, feed: dict, context: Optional[ExtractionContext] = None) -> None:
        items = [item for item in feed.get("items", []) if item.get("link")]
        if not items:
            return

        def worker(item):
            context = self.new_context(source="fulltext", base_url=item["link"])
            try:
                html = self.extractor.fetch(item["link"], self.settings.user_agent, context=context)
            except Exception as exc:
                log.warning("Full-text fetch failed for %s: %s", item["link"], exc)
                return False
            text, kind = extract_fulltext_with_kind(html, url=item["link"])
            if text:
                item["content"] = text
                item["content_kind"] = kind or "text"
            return True

        workers = max(1, min(self.settings.full_text_workers, len(items)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            fetched = list(pool.map(worker, items))
        failed = fetched.count(False)
        if failed:
            message = f"Full text unavailable for {failed} of {len(items)} item(s)"
            if context is not None and context.diagnostics is not None:
                context.diagnostics.warnings.append(message)
            else:
                feed.setdefault("provenance", {}).setdefault("warnings", []).append(message)

    def _worker_service(self):
        """Compatibility helper preserving explicitly configured extensions."""
        return FeedService(
            settings=self.settings,
            use_cache=self.use_cache,
            plugins=self.plugins,
            bridges=self.bridges,
            extensions_loaded=True,
            clock=self.clock,
        )

    def get_feeds(
        self,
        urls: Iterable[str],
        max_workers: int = 4,
        force_refresh: bool = False,
        use_async: Optional[bool] = None,
        runtime: Optional[Dict[str, dict]] = None,
    ) -> Dict[str, dict]:
        """Build feeds for ``urls`` concurrently.

        ``runtime``, when given, is filled per URL with operational facts that
        do not belong in the feed itself: ``elapsed_ms``, ``cache_state`` and
        the ``transport`` actually used.
        """
        urls = list(dict.fromkeys(urls))
        if not urls:
            return {}
        async_enabled = self.settings.use_async if use_async is None else use_async
        if async_enabled:
            from .async_fetch import aiohttp_available

            if aiohttp_available():
                return self._get_feeds_async(urls, max_workers, force_refresh, runtime)
            log.warning("aiohttp unavailable; falling back to threaded transport")

        import threading

        results: Dict[str, dict] = {}
        local = threading.local()

        def worker(url):
            started = time.monotonic()
            service = getattr(local, "service", None)
            if service is None:
                service = self._worker_service()
                local.service = service
            new_context = getattr(service, "new_context", None)
            context = new_context(base_url=url) if new_context else None
            try:
                if context is None:
                    return service.get_feed(url, force_refresh=force_refresh)
                return service.get_feed(url, force_refresh=force_refresh, context=context)
            except Exception as exc:
                return {
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "elapsed_ms": (time.monotonic() - started) * 1000,
                }
            finally:
                if runtime is not None:
                    runtime[url] = {
                        "elapsed_ms": (time.monotonic() - started) * 1000,
                        "cache_state": context.response_meta.get("cache_state")
                        if context is not None
                        else None,
                        "transport": "thread",
                    }

        workers = max(1, min(max_workers, len(urls)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_url = {pool.submit(worker, url): url for url in urls}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    results[url] = future.result()
                except Exception as exc:
                    log.warning("Failed to build feed for %s: %s", url, exc)
                    results[url] = {"error": str(exc), "error_type": type(exc).__name__}
        return {url: results[url] for url in urls}

    def _get_feeds_async(self, urls, max_workers, force_refresh, runtime=None):
        from .async_fetch import fetch_urls_concurrent

        fetch_started = time.monotonic()
        refused = {}
        if self.settings.respect_robots:
            # Same robots.txt rules (and Crawl-delay pacing) as the threaded path.
            for url in urls:
                try:
                    allowed = self.extractor._can_fetch_policy(url, self.settings.user_agent)
                except Exception:  # noqa: BLE001 - unreadable robots.txt allows the fetch
                    allowed = True
                if not allowed:
                    refused[url] = PermissionError(f"robots.txt disallows fetching {url}")
        allowed_urls = [url for url in urls if url not in refused]
        fetched = dict(refused)
        if allowed_urls:
            fetched.update(
                fetch_urls_concurrent(allowed_urls, self.settings, max_workers=max_workers)
            )
        fetch_ms = (time.monotonic() - fetch_started) * 1000
        results = {}
        for url in urls:
            started = time.monotonic()
            if runtime is not None:
                runtime[url] = {"transport": "async", "fetch_phase_ms": fetch_ms}
            payload = fetched.get(url)
            if isinstance(payload, Exception):
                results[url] = {
                    "error": str(payload),
                    "error_type": type(payload).__name__,
                    "elapsed_ms": (time.monotonic() - started) * 1000,
                }
                continue
            try:
                body = payload.body if hasattr(payload, "body") else payload
                context = self.new_context(source="network", base_url=url)
                if hasattr(payload, "effective_url"):
                    context.response_meta = {
                        "effective_url": payload.effective_url,
                        "status": payload.status,
                        "headers": dict(payload.headers),
                        "cache_state": "async_fetch",
                    }
                results[url] = self.get_feed(url, data=body, context=context)
            except Exception as exc:
                results[url] = {
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "elapsed_ms": (time.monotonic() - started) * 1000,
                }
            if runtime is not None:
                runtime[url].update(
                    {
                        "elapsed_ms": fetch_ms + (time.monotonic() - started) * 1000,
                        "cache_state": "async_fetch",
                    }
                )
        return results

    def get_feed_with_diagnostics(self, url: str, **kwargs):
        context = kwargs.pop("context", None) or self.new_context(base_url=url)
        feed = self.get_feed(url, context=context, **kwargs)
        return feed, context.diagnostics

    def get_feed_source(self, source: DocumentSource, **kwargs):
        context = self.new_context(source=source.kind, base_url=source.base_url)
        if context.diagnostics:
            context.diagnostics.metadata["location"] = source.location
        return self.get_feed(
            source.base_url,
            data=source.data if source.is_local else None,
            context=context,
            **kwargs,
        )


MappingLike = Optional[Dict[str, Any]]


def _header_language(meta: Dict[str, Any]) -> Optional[str]:
    headers = meta.get("headers") or {}
    value = headers.get("Content-Language") or headers.get("content-language")
    return value.split(",", 1)[0].split("-", 1)[0].strip().lower() if value else None


def _looks_client_rendered(data: bytes) -> bool:
    sample = data[:512_000].lower()
    has_bundle = b"<script" in sample and any(
        marker in sample
        for marker in (b"webpack", b"__next_data__", b"/_next/", b"vite", b"main.js")
    )
    has_root = any(marker in sample for marker in (b'id="root"', b'id="app"', b'id="__next"'))
    return has_bundle and has_root
