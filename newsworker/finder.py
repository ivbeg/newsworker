#!/usr/bin/env python
"""Modern, bounded RSS/Atom/JSON Feed and sitemap discovery."""

from __future__ import annotations

import concurrent.futures
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
import lxml.etree
from lxml import etree
from lxml.html import fromstring

from .fetch import FetchPolicy, FetchRequest, FetchResult, RequestsTransport
from .settings import Settings

log = logging.getLogger(__name__)
_FEED_TYPES = {
    "application/rss+xml": "rss",
    "application/atom+xml": "atom",
    "application/feed+json": "jsonfeed",
    "application/json": "jsonfeed",
}


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


class FeedsFinder:
    def __init__(self, settings=None, transport=None):
        self.settings = settings or Settings()
        self.transport = transport or RequestsTransport()
        self.policy = FetchPolicy(
            timeout=self.settings.request_timeout,
            max_bytes=self.settings.max_content_bytes,
            verify_tls=self.settings.verify_tls,
            redirect_limit=self.settings.redirect_limit,
            allowed_hosts=tuple(self.settings.allowed_hosts),
            block_private_hosts=self.settings.block_private_hosts,
            allow_private_hosts=self.settings.allow_private_hosts,
            trusted_proxy=self.settings.trusted_proxy,
            proxy=self.settings.proxy or None,
            user_agent=self.settings.user_agent,
            extra_headers=self.settings.extra_headers,
        )

    def _fetch(self, url, *, max_bytes=None):
        policy = self.policy
        if max_bytes is not None:
            from dataclasses import replace

            policy = replace(policy, max_bytes=max_bytes)
        return self.transport.fetch(FetchRequest(url), policy)

    def collect_feeds(self, root, url):
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
        visited = set()
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
    ):
        try:
            fetched = self._fetch(url)
        except Exception as exc:
            # Keep the result shape for library callers, but say that the page
            # itself was unreachable: "no feeds" and "could not look" differ.
            log.error("Failed to fetch %s: %s", url, exc)
            return {"url": url, "items": [], "error": f"{type(exc).__name__}: {exc}"}
        content_type = (fetched.headers.get("Content-Type") or "").split(";", 1)[0].lower()
        root = None
        if content_type in _FEED_TYPES or fetched.body.lstrip().startswith((b"<?xml", b"{")):
            candidate = FeedCandidate(
                fetched.effective_url,
                _FEED_TYPES.get(content_type, "undefined"),
                source=["direct"],
                confidence=1.0,
            ).to_dict()
            items = [candidate if noverify else self._verify(candidate, include_entries)]
        else:
            try:
                root = fromstring(fetched.body, parser=etree.HTMLParser(remove_blank_text=True))
            except (ValueError, lxml.etree.ParserError, lxml.etree.XMLSyntaxError):
                root = None
            items = self.collect_feeds(root, fetched.effective_url) if root is not None else []
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
        if extractrss and root is not None:
            from .extractor import FeedExtractor

            feed, _ = FeedExtractor().get_feed(fetched.effective_url, data=fetched.body)
            if feed.get("items"):
                items.append(
                    {
                        "title": feed["title"],
                        "url": fetched.effective_url,
                        "feedtype": "html",
                        "num_entries": len(feed["items"]),
                        "verification": "valid",
                        "source": ["extraction"],
                    }
                )
        return {"url": fetched.effective_url, "items": items}

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
            continue
        for source in item.get("source") or []:
            if source not in current["source"]:
                current["source"].append(source)
        if current.get("feedtype") == "undefined" and item.get("feedtype") != "undefined":
            current["feedtype"] = item["feedtype"]
        current["confidence"] = max(current.get("confidence", 0), item.get("confidence", 0))
    return list(merged.values())


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
