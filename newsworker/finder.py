#!/usr/bin/env python
"""Modern, bounded RSS/Atom/JSON Feed and sitemap discovery."""

from __future__ import annotations

import concurrent.futures
import heapq
import itertools
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import unquote, urldefrag, urljoin, urlsplit, urlunsplit

import feedparser
import lxml.etree
from lxml import etree
from lxml.html import fromstring

from .consts import CRAWL_SECTION_HINTS, NON_HTML_EXTENSIONS
from .fetch import FetchPolicy, FetchRequest, FetchResult, RequestsTransport
from .settings import Settings
from .tools import ROBOTS_MAX_BYTES, robots_allows

log = logging.getLogger(__name__)
_FEED_TYPES = {
    "application/rss+xml": "rss",
    "application/atom+xml": "atom",
    "application/feed+json": "jsonfeed",
    "application/json": "jsonfeed",
}
_HTML_TYPES = {"text/html", "application/xhtml+xml"}

#: Default bounds of ``find_feeds(crawl=True)``: pages fetched and link steps
#: from the start page.
CRAWL_MAX_PAGES = 50
CRAWL_MAX_DEPTH = 2
#: Dated items a page needs to be reported as a news listing.
MIN_LISTING_ITEMS = 3
#: Pages kept in a crawled candidate's ``found_on``.
FOUND_ON_KEPT = 5
_PAGINATION = re.compile(r"/page/\d+/?$|[?&](?:page|p|offset|start)=", re.IGNORECASE)


@dataclass
class FeedCandidate:
    url: str
    feedtype: str = "undefined"
    title: str | None = None
    source: list[str] = field(default_factory=list)
    confidence: float = 0.5
    verification: str = "unverified"
    verification_error: str | None = None
    num_entries: int | None = None
    language: str | None = None
    hubs: list[str] = field(default_factory=list)
    self_url: str | None = None
    entries: list | None = None

    def to_dict(self):
        data = {
            "title": self.title or self.url,
            "url": self.url,
            "feedtype": self.feedtype,
            "source": list(self.source),
            "confidence": self.confidence,
            "verification": self.verification,
        }
        for name in (
            "verification_error",
            "num_entries",
            "language",
            "hubs",
            "self_url",
            "entries",
        ):
            value = getattr(self, name)
            if value not in (None, [], ""):
                data[name] = value
        return data


def _normalized(url):
    parsed = urlsplit(url)
    return urlunsplit(
        (
            parsed.scheme.lower(),
            (parsed.hostname or "").lower() + ((":" + str(parsed.port)) if parsed.port else ""),
            parsed.path or "/",
            parsed.query,
            "",
        )
    )


def _feedlike(url):
    low = url.lower()
    return low.endswith((".rss", ".atom", ".xml", ".json")) or any(
        marker in low for marker in ("/feed", "/rss", "/atom", "jsonfeed")
    )


def _site(url):
    """The host a crawl stays on; ``www.example.com`` and ``example.com`` are one site."""
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _parse_html(body):
    try:
        return fromstring(body, parser=etree.HTMLParser(remove_blank_text=True))
    except (ValueError, lxml.etree.ParserError, lxml.etree.XMLSyntaxError):
        return None


def _is_html(fetched):
    content_type = (fetched.header("Content-Type") or "").split(";", 1)[0].strip().lower()
    if content_type:
        return content_type in _HTML_TYPES
    return not fetched.body.lstrip().startswith((b"<?xml", b"{", b"%PDF"))


def _page_links(root, base_url, site):
    """Same-site links of ``root`` worth visiting as pages, with their anchor text."""
    for anchor in root.xpath("//a[@href]"):
        try:
            link = urldefrag(urljoin(base_url, (anchor.get("href") or "").strip())).url
            parts = urlsplit(link)
            _normalized(link)
        except ValueError:
            continue
        if parts.scheme not in {"http", "https"} or _site(link) != site:
            continue
        if parts.path.lower().endswith(NON_HTML_EXTENSIONS) or _feedlike(link):
            continue
        yield link, " ".join("".join(anchor.itertext()).split()).lower()


def _link_score(url, text):
    """Visit order among links at one depth: news sections first, pagination last."""
    parts = urlsplit(url)
    if _PAGINATION.search(parts.path + ("?" + parts.query if parts.query else "")):
        return -1
    path = unquote(parts.path).lower()
    hint = any(word in path or word in text for word in CRAWL_SECTION_HINTS)
    shallow = len([segment for segment in path.split("/") if segment]) <= 2
    return (2 if hint else 0) + (1 if shallow else 0)


class FeedsFinder:
    def __init__(self, settings=None, transport=None):
        self.settings = settings or Settings()
        self.transport = transport or RequestsTransport()
        self.policy = FetchPolicy(
            timeout=self.settings.request_timeout,
            max_bytes=self.settings.max_content_bytes,
            verify_tls=self.settings.verify_tls,
            legacy_tls_ciphers=self.settings.legacy_tls_ciphers,
            redirect_limit=self.settings.redirect_limit,
            allowed_hosts=tuple(self.settings.allowed_hosts),
            block_private_hosts=self.settings.block_private_hosts,
            allow_private_hosts=self.settings.allow_private_hosts,
            trusted_proxy=self.settings.trusted_proxy,
            proxy=self.settings.proxy or None,
            user_agent=self.settings.user_agent,
            extra_headers=self.settings.extra_headers,
        )
        self._service = None

    def _fetch(self, url, *, max_bytes=None):
        if self.settings.respect_robots and not self._robots_allows(url):
            raise PermissionError("robots.txt disallows fetching %s" % url)
        policy = self.policy
        if max_bytes is not None:
            policy = replace(policy, max_bytes=max_bytes)
        return self.transport.fetch(FetchRequest(url), policy)

    def _robots_allows(self, url):
        """Consult robots.txt through the same transport and policy, as
        ``FeedExtractor`` does, and apply its ``Crawl-delay`` to the host."""
        policy = replace(self.policy, max_bytes=min(self.policy.max_bytes, ROBOTS_MAX_BYTES))
        return robots_allows(
            url,
            lambda robots_url: self.transport.fetch(FetchRequest(robots_url), policy).body,
            self.settings.user_agent,
        )

    def collect_feeds(self, root, url):  # noqa: C901
        candidates: dict[str, FeedCandidate] = {}
        page_hubs = []
        page_self = None
        for relation in root.xpath("//link[@href]"):
            rels = {part.lower() for part in (relation.get("rel") or "").split()}
            if "hub" in rels:
                page_hubs.append(urljoin(url, relation.get("href")))
            if "self" in rels:
                page_self = urljoin(url, relation.get("href"))

        def add(raw_url, feedtype="undefined", source="heuristic", confidence=0.5, title=None):
            if not raw_url:
                return
            absolute = urljoin(url, raw_url.strip())
            if urlsplit(absolute).scheme not in {"http", "https"}:
                return
            key = _normalized(absolute)
            candidate = candidates.get(key)
            if candidate is None:
                candidate = FeedCandidate(
                    absolute,
                    feedtype=feedtype,
                    title=title,
                    source=[source],
                    confidence=confidence,
                    hubs=list(dict.fromkeys(page_hubs)),
                    self_url=page_self,
                )
                candidates[key] = candidate
            else:
                if source not in candidate.source:
                    candidate.source.append(source)
                if candidate.feedtype == "undefined" and feedtype != "undefined":
                    candidate.feedtype = feedtype
                candidate.confidence = max(candidate.confidence, confidence)
                candidate.title = candidate.title or title

        for link in root.xpath("//link[@href]"):
            rels = {part.lower() for part in (link.get("rel") or "").split()}
            media_type = (link.get("type") or "").split(";", 1)[0].strip().lower()
            if "alternate" in rels and media_type in _FEED_TYPES:
                add(
                    link.get("href"),
                    _FEED_TYPES[media_type],
                    "autodiscovery",
                    1.0,
                    link.get("title"),
                )
        for anchor in root.xpath("//a[@href]"):
            href = anchor.get("href") or ""
            text = " ".join("".join(anchor.itertext()).split()).lower()
            if _feedlike(href) or "rss" in text or text == "feed":
                kind = (
                    "atom"
                    if "atom" in href.lower()
                    else "rss"
                    if "rss" in (href + text).lower()
                    else "undefined"
                )
                add(href, kind, "link-heuristic", 0.5, anchor.get("title"))
        for image in root.xpath("//a[@href]/img[@src]"):
            marker = ((image.get("src") or "") + " " + (image.get("alt") or "")).lower()
            if "rss" in marker or "feed" in marker:
                add(image.getparent().get("href"), "rss", "feed-icon", 0.6, image.get("alt"))
        return [candidate.to_dict() for candidate in candidates.values()]

    def discover_sitemap_feeds(
        self,
        base_url,
        timeout=30,
        *,
        max_depth=3,
        max_documents=25,
        max_urls=5000,
        max_bytes=2 * 1024 * 1024,
    ):
        start = urljoin(base_url, "/sitemap.xml")
        queue = [(start, 0)]
        visited: set[str] = set()
        candidates: dict[str, FeedCandidate] = {}
        urls_seen = 0
        while queue and len(visited) < max_documents and urls_seen < max_urls:
            sitemap_url, depth = queue.pop(0)
            key = _normalized(sitemap_url)
            if key in visited or depth > max_depth:
                continue
            visited.add(key)
            try:
                result = self._fetch(sitemap_url, max_bytes=max_bytes)
                document = lxml.etree.fromstring(result.body)
            except Exception as exc:
                log.debug("No usable sitemap at %s: %s", sitemap_url, exc)
                continue
            root_name = document.tag.rsplit("}", 1)[-1] if isinstance(document.tag, str) else ""
            locations = [
                (element.text or "").strip()
                for element in document.iter()
                if isinstance(element.tag, str) and element.tag.rsplit("}", 1)[-1] == "loc"
            ]
            for location in locations:
                if not location:
                    continue
                urls_seen += 1
                if urls_seen > max_urls:
                    break
                absolute = urljoin(sitemap_url, location)
                if root_name == "sitemapindex":
                    queue.append((absolute, depth + 1))
                elif _feedlike(absolute):
                    normalized = _normalized(absolute)
                    candidate = candidates.get(normalized)
                    if candidate is None:
                        candidate = FeedCandidate(
                            absolute,
                            "atom" if "atom" in absolute.lower() else "rss",
                            source=[f"sitemap:{sitemap_url}"],
                            confidence=0.6,
                        )
                        candidates[normalized] = candidate
                    elif f"sitemap:{sitemap_url}" not in candidate.source:
                        candidate.source.append(f"sitemap:{sitemap_url}")
        return [candidate.to_dict() for candidate in candidates.values()]

    def _verify(self, candidate, include_entries=False):
        result = dict(candidate)
        try:
            fetched = self._fetch(candidate["url"])
            parsed = self._parse_feed(
                fetched, candidate.get("feedtype", "undefined"), include_entries
            )
            result.update(parsed)
            result["verification"] = "valid"
        except Exception as exc:
            result["verification"] = "invalid"
            result["verification_error"] = f"{type(exc).__name__}: {exc}"
        return result

    def _parse_feed(self, fetched: FetchResult, declared_type, include_entries):
        content_type = (fetched.headers.get("Content-Type") or "").split(";", 1)[0].lower()
        kind = _FEED_TYPES.get(content_type, declared_type)
        if kind == "jsonfeed" or fetched.body.lstrip().startswith(b"{"):
            data = json.loads(fetched.body.decode("utf-8"))
            version = data.get("version", "")
            if (
                not isinstance(version, str)
                or "jsonfeed.org/version" not in version
                or not isinstance(data.get("items"), list)
            ):
                raise ValueError("document is not a valid JSON Feed")
            parsed = {
                "title": data.get("title") or fetched.effective_url,
                "url": fetched.effective_url,
                "feedtype": "jsonfeed",
                "num_entries": len(data["items"]),
            }
            if data.get("language"):
                parsed["language"] = data["language"]
            if include_entries:
                parsed["entries"] = data["items"]
            hubs = [
                hub.get("url")
                for hub in data.get("hubs", [])
                if isinstance(hub, dict) and hub.get("url")
            ]
            if hubs:
                parsed["hubs"] = hubs
            return parsed
        document = feedparser.parse(fetched.body)
        if document.bozo and not document.entries and not document.feed:
            raise ValueError("document is not a valid RSS or Atom feed")
        if not document.feed.get("title") and not document.entries:
            raise ValueError("feed has neither metadata nor entries")
        feedtype = "atom" if str(document.version).startswith("atom") else "rss"
        parsed = {
            "title": document.feed.get("title") or fetched.effective_url,
            "url": fetched.effective_url,
            "feedtype": feedtype,
            "num_entries": len(document.entries),
        }
        if document.feed.get("language"):
            parsed["language"] = document.feed.language
        if include_entries:
            parsed["entries"] = document.entries
        hubs, self_url = [], None
        for link in document.feed.get("links", []):
            rel = link.get("rel")
            if rel == "hub" and link.get("href"):
                hubs.append(link["href"])
            elif rel == "self" and link.get("href"):
                self_url = link["href"]
        if hubs:
            parsed["hubs"] = hubs
        if self_url:
            parsed["self_url"] = self_url
        return parsed

    def find_feeds(
        self,
        url,
        noverify=True,
        force_htmlparse=False,
        include_entries=False,
        extractrss=False,
        crawl=False,
        timeout=30,
        include_sitemap=False,
        max_workers=8,
        max_pages=CRAWL_MAX_PAGES,
        max_depth=CRAWL_MAX_DEPTH,
    ):
        """Feeds ``url`` declares or is, as ``{"url", "items"}``.

        ``crawl`` also visits same-site pages, at most ``max_pages`` of them and
        ``max_depth`` link steps away, and adds ``found_on`` to each candidate
        and a ``crawl`` summary to the result. ``extractrss`` reports pages that
        extraction reads as a news listing as ``html`` candidates.
        """
        if crawl and (max_pages < 1 or max_depth < 1):
            raise ValueError("max_pages and max_depth must be positive")
        try:
            fetched = self._fetch(url)
        except Exception as exc:
            # Keep the result shape for library callers, but say that the page
            # itself was unreachable: "no feeds" and "could not look" differ.
            log.error("Failed to fetch %s: %s", url, exc)
            return {"url": url, "items": [], "error": f"{type(exc).__name__}: {exc}"}
        content_type = (fetched.headers.get("Content-Type") or "").split(";", 1)[0].lower()
        listings: list[dict[str, Any]] = []
        summary = None
        if content_type in _FEED_TYPES or fetched.body.lstrip().startswith((b"<?xml", b"{")):
            candidate = FeedCandidate(
                fetched.effective_url,
                _FEED_TYPES.get(content_type, "undefined"),
                source=["direct"],
                confidence=1.0,
            ).to_dict()
            items = [candidate if noverify else self._verify(candidate, include_entries)]
            if crawl:
                summary = _crawl_summary(1, max_pages, max_depth, False, {})
        elif crawl:
            items, listings, summary = self._crawl(
                fetched, max_pages=max_pages, max_depth=max_depth, listings=extractrss
            )
        else:
            root = _parse_html(fetched.body)
            items = self.collect_feeds(root, fetched.effective_url) if root is not None else []
            if extractrss and root is not None:
                listing = self._listing(fetched.effective_url, fetched.body)
                listings = [listing] if listing else []
        if include_sitemap:
            items.extend(self.discover_sitemap_feeds(fetched.effective_url, timeout=timeout))
        items = _merge_candidates(items)
        if not noverify and items:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max(1, min(max_workers, len(items)))
            ) as pool:
                items = list(pool.map(lambda item: self._verify(item, include_entries), items))
        elif noverify:
            for item in items:
                item["verification"] = "unverified"
        items.extend(listings)
        result = {"url": fetched.effective_url, "items": items}
        if summary is not None:
            for item in items:
                item.setdefault("found_on", [])
                item.setdefault("found_on_count", 0)
            result["crawl"] = summary
        return result

    def _crawl(self, start, *, max_pages, max_depth, listings):
        """Visit same-site pages from ``start`` one at a time, nearest first and
        news sections before other links, and collect candidates on each.

        Returns the feed candidates, the listing candidates and the summary.
        """
        site = _site(start.effective_url)
        frontier: list[tuple[int, int, int, str]] = []
        order = itertools.count()
        queued = {_normalized(start.requested_url), _normalized(start.effective_url)}
        visited: set[str] = set()
        items: list[dict[str, Any]] = []
        found_listings: list[dict[str, Any]] = []
        skipped = {"robots": 0, "error": 0, "not_html": 0}
        fetched_pages = 0
        page, depth = start, 0
        while page is not None:
            fetched_pages += 1
            page_url = page.effective_url
            key = _normalized(page_url)
            root = None
            if key in visited:
                pass  # a redirect to a page already crawled
            elif not _is_html(page):
                skipped["not_html"] += 1
            else:
                root = _parse_html(page.body)
            visited.add(key)
            if root is not None:
                log.info("Crawled %s (depth %d)", page_url, depth)
                for item in self.collect_feeds(root, page_url):
                    items.append({**item, "found_on": [page_url], "found_on_count": 1})
                listing = self._listing(page_url, page.body) if listings else None
                if listing:
                    found_listings.append({**listing, "found_on": [page_url], "found_on_count": 1})
                if depth < max_depth:
                    for link, text in _page_links(root, page_url, site):
                        link_key = _normalized(link)
                        if link_key not in queued:
                            queued.add(link_key)
                            score = _link_score(link, text)
                            heapq.heappush(frontier, (depth + 1, -score, next(order), link))
            page = None
            # Failed requests count against the bound; robots.txt refusals send none.
            while frontier and fetched_pages + skipped["error"] < max_pages:
                depth, _, _, link = heapq.heappop(frontier)
                if self.settings.respect_robots and not self._robots_allows(link):
                    skipped["robots"] += 1
                    continue
                try:
                    page = self._fetch(link)
                except Exception as exc:  # noqa: BLE001 - one bad page does not stop the crawl
                    log.debug("Skipping %s: %s", link, exc)
                    skipped["error"] += 1
                    continue
                break
        summary = _crawl_summary(fetched_pages, max_pages, max_depth, bool(frontier), skipped)
        return items, found_listings, summary

    def _listing(self, url, body):
        """An ``html`` candidate when extraction reads ``body`` as a news listing."""
        if self._service is None:
            from .service import FeedService

            # No caches: a scan must not store a spec for every page it reads.
            self._service = FeedService(self.settings, use_cache=False)
        try:
            feed, diagnostics = self._service.get_feed_with_diagnostics(url, data=body)
        except Exception as exc:  # noqa: BLE001 - a page that fails extraction is no listing
            log.debug("No news listing on %s: %s", url, exc)
            return None
        entries = feed.get("items") or []
        if sum(1 for entry in entries if entry.get("pubdate")) < MIN_LISTING_ITEMS:
            return None
        listing = {
            "title": feed.get("title") or url,
            "url": url,
            "feedtype": "html",
            "source": ["extraction"],
            "confidence": diagnostics.confidence if diagnostics else 0.5,
            "verification": "valid",
            "num_entries": len(entries),
        }
        if feed.get("language"):
            listing["language"] = feed["language"]
        return listing

    def find_feeds_deep(self, url, lookin=True):
        return self.find_feeds(url, noverify=False, force_htmlparse=lookin)


def _merge_candidates(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        key = _normalized(item["url"])
        current = merged.get(key)
        if current is None:
            merged[key] = dict(item)
            merged[key]["source"] = list(item.get("source") or [])
            if "found_on" in item:
                merged[key]["found_on"] = list(item["found_on"])[:FOUND_ON_KEPT]
            continue
        for source in item.get("source") or []:
            if source not in current["source"]:
                current["source"].append(source)
        if current.get("feedtype") == "undefined" and item.get("feedtype") != "undefined":
            current["feedtype"] = item["feedtype"]
        current["confidence"] = max(current.get("confidence", 0), item.get("confidence", 0))
        if "found_on" in item:
            pages = current.setdefault("found_on", [])
            for page in item["found_on"]:
                if page not in pages and len(pages) < FOUND_ON_KEPT:
                    pages.append(page)
            current["found_on_count"] = current.get("found_on_count", 0) + item.get(
                "found_on_count", 0
            )
    return list(merged.values())


def _crawl_summary(pages_fetched, max_pages, max_depth, truncated, skipped):
    return {
        "pages_fetched": pages_fetched,
        "max_pages": max_pages,
        "max_depth": max_depth,
        "truncated": truncated,
        "skipped": {"robots": 0, "error": 0, "not_html": 0, **skipped},
    }


def get_url_data(url):
    """Compatibility helper returning parsed HTML and effective URL."""
    finder = FeedsFinder()
    try:
        fetched = finder._fetch(url)
        root = fromstring(fetched.body, parser=etree.HTMLParser(remove_blank_text=True))
        return root, fetched.effective_url
    except Exception as exc:
        log.warning("Failed to parse HTML from %s: %s", url, exc)
        return None, None
