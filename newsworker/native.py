"""Native feeds (RSS, Atom, JSON Feed) normalised to the internal feed dict.

When a URL already serves a feed there is nothing to extract: the entries are
mapped onto the same item contract the HTML strategies produce, keeping the
publisher's entry ids, dates, authors, categories and content.
"""

from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import json
from collections.abc import Mapping
from typing import Any, cast

from .model import Feed
from .tools import clean_url, get_abs_url, parse_datetime_attr

_FEED_TYPES = (
    "application/rss+xml",
    "application/atom+xml",
    "application/feed+json",
    "application/json",
    "application/xml",
    "text/xml",
    "application/rdf+xml",
)
_XML_MARKERS = (b"<rss", b"<feed", b"<rdf:rdf")


def looks_like_feed(data: bytes, content_type: str | None = None) -> bool:
    """Cheap check: does this response carry a feed rather than an HTML page?"""
    head = data[:2048].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return False
    if head.startswith(b"{"):
        return b"jsonfeed.org/version" in data[:4096]
    if any(marker in head for marker in _XML_MARKERS):
        return True
    kind = (content_type or "").split(";", 1)[0].strip().lower()
    return kind in _FEED_TYPES and head.startswith(b"<?xml")


def _struct_time(value) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromtimestamp(calendar.timegm(value), tz=dt.timezone.utc)
    except (OverflowError, TypeError, ValueError):
        return None


def _identity(*parts: str | None) -> str:
    for part in parts:
        if part:
            return hashlib.md5(
                ("native:" + part).encode("utf-8"), usedforsecurity=False
            ).hexdigest()
    return ""


def _item(
    *,
    entry_id,
    link,
    title,
    description,
    pubdate,
    author,
    categories,
    content,
    content_kind,
    image,
    base,
):
    link = clean_url(get_abs_url(base, link)) if link else None
    item: dict[str, Any] = {
        "title": title,
        "description": description or title,
        "pubdate": pubdate,
        "link": link,
        "unique_id": _identity(entry_id, link, title),
        "native_id": entry_id or None,
        "extra": {"links": [link] if link else [], "images": [image] if image else []},
    }
    if author:
        item["author"] = author
    if categories:
        item["categories"] = categories
    if content:
        item["content"] = content
        item["content_kind"] = content_kind
    return item


def _from_feedparser(data: bytes, url: str) -> dict[str, Any] | None:
    import feedparser

    parsed = feedparser.parse(data)
    if not parsed.get("version") or not parsed.entries and not parsed.feed:
        return None
    feed_meta = parsed.feed
    base = feed_meta.get("link") or url
    items: list[dict[str, Any]] = []
    for entry in parsed.entries:
        content = None
        content_kind = "text"
        if entry.get("content"):
            first = entry["content"][0]
            content = first.get("value")
            content_kind = "html" if "html" in (first.get("type") or "") else "text"
        image = None
        for enclosure in entry.get("enclosures") or []:
            if str(enclosure.get("type", "")).startswith("image/"):
                image = enclosure.get("href")
                break
        items.append(
            _item(
                entry_id=entry.get("id"),
                link=entry.get("link"),
                title=entry.get("title"),
                description=entry.get("summary"),
                pubdate=_struct_time(entry.get("published_parsed"))
                or _struct_time(entry.get("updated_parsed")),
                author=entry.get("author"),
                categories=[tag.get("term") for tag in entry.get("tags") or [] if tag.get("term")],
                content=content,
                content_kind=content_kind,
                image=image,
                base=base,
            )
        )
    return {
        "title": feed_meta.get("title") or url,
        "link": feed_meta.get("link") or url,
        "description": feed_meta.get("subtitle") or feed_meta.get("title") or url,
        "language": (feed_meta.get("language") or "").split("-")[0].lower() or None,
        "items": items,
        "native_format": parsed.get("version"),
    }


def _from_json_feed(data: bytes, url: str, default_timezone: str) -> dict[str, Any] | None:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(document, Mapping) or "jsonfeed.org/version" not in str(
        document.get("version", "")
    ):
        return None
    base = document.get("home_page_url") or url
    items = []
    for entry in document.get("items") or []:
        if not isinstance(entry, Mapping):
            continue
        published = entry.get("date_published") or entry.get("date_modified")
        authors = entry.get("authors") or ([entry["author"]] if entry.get("author") else [])
        author = next(
            (a.get("name") for a in authors if isinstance(a, Mapping) and a.get("name")), None
        )
        html = entry.get("content_html")
        items.append(
            _item(
                entry_id=str(entry["id"]) if entry.get("id") is not None else None,
                link=entry.get("url") or entry.get("external_url"),
                title=entry.get("title"),
                description=entry.get("summary"),
                pubdate=parse_datetime_attr(published, default_timezone=default_timezone)
                if published
                else None,
                author=author,
                categories=[str(tag) for tag in entry.get("tags") or []],
                content=html or entry.get("content_text"),
                content_kind="html" if html else "text",
                image=entry.get("image") or entry.get("banner_image"),
                base=base,
            )
        )
    return {
        "title": document.get("title") or url,
        "link": document.get("home_page_url") or url,
        "description": document.get("description") or document.get("title") or url,
        "language": (document.get("language") or "").split("-")[0].lower() or None,
        "items": items,
        "native_format": "jsonfeed",
    }


def parse_native_feed(
    data: bytes, url: str, *, content_type: str | None = None, default_timezone: str = "UTC"
) -> Feed | None:
    """Return the internal feed dict for a native feed, or ``None`` if it is not one."""
    if not looks_like_feed(data, content_type):
        return None
    if data.lstrip()[:1] == b"{":
        return cast("Feed | None", _from_json_feed(data, url, default_timezone))
    return cast("Feed | None", _from_feedparser(data, url))
