#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
High level feed service combining caching with extraction.

:class:`FeedService` is the shared building block used by both the ``extract``
CLI command and the local HTTP server. It ties together:

* :class:`newsworker.cache.ContentCache` -- avoids re-fetching a page while its
  cached copy is fresh;
* :class:`newsworker.cache.SpecCache` -- reuses a previously built parsing spec,
  building one dynamically on the first request for a URL;
* extraction -- applies the spec with :class:`newsworker.spec.SpecExtractor`, or
  falls back to the fully dynamic :class:`newsworker.extractor.FeedExtractor`
  when no usable spec could be produced.

Cached page content is threaded through the ``data=`` parameter of both
extractors so a single fetch serves both spec building and extraction.
"""

import concurrent.futures
import logging
import threading

from .bridges import default_bridge_dirs, load_bridges, select_bridge
from .cache import ContentCache, SpecCache
from .enrich import enrich_feed, extract_fulltext
from .extractor import FeedExtractor
from .plugins import load_plugins, select_plugin
from .settings import Settings
from .spec import SpecAnalyzer, SpecExtractor
from .tools import decode_html, find_next_link

log = logging.getLogger(__name__)


class FeedService:
    """Builds feeds from URLs with spec and content caching."""

    def __init__(self, settings=None, use_cache=True, plugins=None, bridges=None):
        self.settings = settings or Settings()
        self.use_cache = use_cache
        self.plugins = load_plugins(extra=plugins)
        if bridges is not None:
            self.bridges = bridges
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

    def _fetch(self, url, force_refresh=False):
        """Returns page bytes, honoring the content cache unless refreshing.

        A fresh cache entry is returned directly. A stale-but-present entry is
        revalidated conditionally against the upstream (``If-None-Match`` /
        ``If-Modified-Since``); a ``304`` reuses the cached bytes and refreshes
        their freshness clock, saving bandwidth.
        """
        if self.use_cache and not force_refresh:
            cached = self.content_cache.get(url)
            if cached is not None:
                log.debug("Content cache hit for %s", url)
                return cached
            stale = self.content_cache.get_stale(url)
            if stale is not None:
                meta = self.content_cache.get_meta(url)
                if meta:
                    revalidated = self.extractor.fetch(
                        url, self.settings.user_agent, conditional=meta
                    )
                    if revalidated is None:
                        log.debug("Upstream 304 for %s, reusing cached content", url)
                        self.content_cache.touch(url)
                        return stale
                    self._store_content(url, revalidated)
                    return revalidated
        data = self.extractor.fetch(url, self.settings.user_agent)
        if self.use_cache:
            self._store_content(url, data)
        return data

    def _store_content(self, url, data):
        try:
            self.content_cache.set(
                url, data, meta=getattr(self.extractor, "last_response_meta", None)
            )
        except OSError as e:
            log.warning("Failed to cache content for %s: %s", url, e)

    def _get_or_build_spec(self, url, data):
        """Returns a cached spec, or builds and caches one dynamically."""
        if self.use_cache:
            spec = self.spec_cache.get(url)
            if spec is not None:
                log.debug("Spec cache hit for %s", url)
                return spec
        analyzer = SpecAnalyzer(extractor=self.extractor)
        spec = analyzer.analyze(url, data=data, user_agent=self.settings.user_agent)
        if self.use_cache and spec is not None and spec.fields:
            try:
                self.spec_cache.set(url, spec)
                log.debug("Spec cached for %s", url)
            except OSError as e:
                log.warning("Failed to cache spec for %s: %s", url, e)
        return spec

    def get_feed(
        self, url, force_refresh=False, explicit_spec=None, max_pages=1, data=None
    ):
        """Returns the internal feed dictionary for ``url``.

        :param force_refresh: bypass the content cache and re-fetch the page.
        :param explicit_spec: use this :class:`FeedSpec` instead of the cache.
        :param max_pages: follow up to this many "next" links, merging items.
        :param data: optional pre-fetched page bytes (skips the fetch step).
        """
        if data is None:
            data = self._fetch(url, force_refresh=force_refresh)

        plugin = select_plugin(url, self.plugins)
        if plugin is not None:
            feed = plugin.extract(
                url, data=data, user_agent=self.settings.user_agent
            )
            enrich_feed(feed)
            if self.settings.full_text:
                self._add_full_text(feed)
            return feed

        spec = explicit_spec
        if spec is None:
            bridge_spec = select_bridge(url, self.bridges)
            if bridge_spec is not None:
                spec = bridge_spec
            else:
                spec = self._get_or_build_spec(url, data)

        feed = self._extract_page(url, data, spec)
        if max_pages and max_pages > 1:
            self._follow_pagination(url, data, spec, feed, max_pages)

        enrich_feed(feed)
        if self.settings.full_text:
            self._add_full_text(feed)
        return feed

    def _extract_page(self, url, data, spec):
        """Extracts a single page using ``spec`` when usable, else dynamically."""
        if spec is not None and spec.fields:
            return SpecExtractor(extractor=self.extractor).extract(
                url, spec, data=data, user_agent=self.settings.user_agent
            )
        log.debug("No usable spec for %s, using dynamic extraction", url)
        feed, _session = self.extractor.get_feed(
            url, data=data, user_agent=self.settings.user_agent
        )
        return feed

    def _follow_pagination(self, url, data, spec, feed, max_pages):
        """Follows "next" links up to ``max_pages``, merging their items in place."""
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
            except Exception:  # noqa: BLE001
                break
            nxt = find_next_link(doc, current_url)
            if not nxt or nxt in visited:
                break
            visited.add(nxt)
            try:
                next_data = self._fetch(nxt)
            except Exception as e:  # noqa: BLE001
                log.debug("Pagination fetch failed for %s: %s", nxt, e)
                break
            page_spec = spec
            if page_spec is None or not page_spec.fields:
                page_spec = self._get_or_build_spec(nxt, next_data)
            page_feed = self._extract_page(nxt, next_data, page_spec)
            feed.setdefault("items", []).extend(page_feed.get("items", []))
            current_url, current_data = nxt, next_data
            pages += 1

    def _add_full_text(self, feed):
        """Fetches each item link and populates ``content`` with the main body.

        Uses bounded concurrency and degrades gracefully when the optional
        full-text dependency is missing or a fetch fails.
        """
        items = [i for i in feed.get("items", []) if i.get("link")]
        if not items:
            return

        def worker(item):
            try:
                html = self.extractor.fetch(item["link"], self.settings.user_agent)
            except Exception as e:  # noqa: BLE001
                log.debug("Full-text fetch failed for %s: %s", item["link"], e)
                return
            if html is None:
                return
            text = extract_fulltext(html, url=item["link"])
            if text:
                item["content"] = text

        workers = max(1, min(self.settings.full_text_workers, len(items)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(worker, items))

    def _worker_service(self):
        """Creates an independent service for use inside a worker thread.

        A :class:`FeedExtractor` keeps per-run mutable state (the debug session
        and the date-parser session), so it is not safe to share one across
        threads. Each worker therefore gets its own service instance.
        """
        return FeedService(settings=self.settings, use_cache=self.use_cache)

    def get_feeds(self, urls, max_workers=4, force_refresh=False, use_async=None):
        """Builds feeds for many URLs concurrently.

        Returns a ``{url: feed}`` mapping. A URL that fails is mapped to an
        ``{"error": <message>}`` dict instead of aborting the whole batch. Each
        worker thread uses its own :class:`FeedService` (see
        :meth:`_worker_service`).

        When ``use_async`` is true (or :attr:`Settings.use_async`), pages are
        fetched with the optional aiohttp transport before extraction.
        """
        urls = list(dict.fromkeys(urls))  # de-duplicate, preserve order
        if not urls:
            return {}

        async_enabled = self.settings.use_async if use_async is None else use_async
        if async_enabled:
            return self._get_feeds_async(urls, max_workers, force_refresh)

        local = threading.local()

        def worker(url):
            service = getattr(local, "service", None)
            if service is None:
                service = self._worker_service()
                local.service = service
            return service.get_feed(url, force_refresh=force_refresh)

        results = {}
        workers = max(1, min(max_workers, len(urls)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_url = {pool.submit(worker, url): url for url in urls}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    results[url] = future.result()
                except Exception as e:  # noqa: BLE001 - report per-URL failures
                    log.warning("Failed to build feed for %s: %s", url, e)
                    results[url] = {"error": str(e)}
        return results

    def _get_feeds_async(self, urls, max_workers, force_refresh):
        from .async_fetch import aiohttp_available, fetch_urls_concurrent

        if not aiohttp_available():
            log.warning(
                "Async transport requested but aiohttp is not installed; "
                "falling back to threads. Install with: pip install 'newsworker[async]'"
            )
            return self.get_feeds(
                urls, max_workers=max_workers, force_refresh=force_refresh, use_async=False
            )

        try:
            fetched = fetch_urls_concurrent(urls, self.settings, max_workers=max_workers)
        except Exception as e:  # noqa: BLE001
            log.warning("Async batch fetch failed (%s); falling back to threads", e)
            return self.get_feeds(
                urls, max_workers=max_workers, force_refresh=force_refresh, use_async=False
            )

        results = {}
        for url in urls:
            payload = fetched.get(url)
            if isinstance(payload, Exception):
                results[url] = {"error": str(payload)}
                continue
            try:
                worker = self._worker_service()
                results[url] = worker.get_feed(
                    url, force_refresh=force_refresh, data=payload
                )
            except Exception as e:  # noqa: BLE001
                log.warning("Failed to build feed for %s: %s", url, e)
                results[url] = {"error": str(e)}
        return results
