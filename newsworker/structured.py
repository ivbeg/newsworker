"""News items published as structured data (JSON-LD and microdata).

Many CMSes describe their listings for search engines: an ``ItemList`` of
articles, a ``@graph`` of ``NewsArticle`` objects, or ``itemprop`` markup with
``datePublished``. Those carry exact, timezone-aware dates and canonical URLs,
so they are used to fill pages where no dates are visible and to sharpen the
dates found by the heuristics.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable
from typing import Any

from .tools import clean_url, get_abs_url, is_safe_link, parse_datetime_attr

ARTICLE_TYPES = {
    "article",
    "newsarticle",
    "blogposting",
    "reportagenewsarticle",
    "analysisnewsarticle",
    "pressrelease",
    "scholarlyarticle",
    "techarticle",
    "socialmediaposting",
    "liveblogposting",
    "event",
}
_TYPE_TAIL = re.compile(r"[/#]")


def _types(node: dict[str, Any]) -> list[str]:
    raw = node.get("@type") or node.get("type") or []
    if isinstance(raw, str):
        raw = [raw]
    return [_TYPE_TAIL.split(str(value))[-1].lower() for value in raw if value]


def _text(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("name") or value.get("@value") or value.get("url")
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _url(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("@id") or value.get("url")
    return str(value).strip() if value else None


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    """Every JSON object nested anywhere in a JSON-LD document."""
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            yield current
            stack.extend(reversed(list(current.values())))
        elif isinstance(current, list):
            stack.extend(reversed(current))


def _json_ld_documents(document) -> list[Any]:
    documents = []
    for script in document.xpath(
        "//script[translate(@type, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
        "='application/ld+json']"
    ):
        raw = (script.text or "").strip()
        if not raw:
            continue
        try:
            documents.append(json.loads(raw))
        except ValueError:
            # Some CMSes emit trailing commas or several objects; skip them.
            continue
    return documents


def _item(node: dict[str, Any], base_url: str, default_timezone: str) -> dict[str, Any] | None:
    url = _url(node.get("url")) or _url(node.get("mainEntityOfPage")) or _url(node.get("@id"))
    title = _text(node.get("headline")) or _text(node.get("name"))
    if not url or not title:
        return None
    link = clean_url(get_abs_url(base_url, url))
    if not is_safe_link(link):
        return None
    published = _text(node.get("datePublished")) or _text(node.get("startDate"))
    pubdate = (
        parse_datetime_attr(published, default_timezone=default_timezone) if published else None
    )
    item: dict[str, Any] = {
        "title": title,
        "link": link,
        "pubdate": pubdate,
        "description": _text(node.get("description")) or title,
    }
    author = node.get("author")
    if isinstance(author, list):
        author = author[0] if author else None
    author_name = _text(author)
    if author_name and not author_name.startswith("http"):
        item["author"] = author_name
    image = _url(node.get("image")) or _url(node.get("thumbnailUrl"))
    if image:
        image = clean_url(get_abs_url(base_url, image))
        if is_safe_link(image):
            item["image"] = image
    return item


def _from_json_ld(document, base_url: str, default_timezone: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for data in _json_ld_documents(document):
        for node in _walk(data):
            types = set(_types(node))
            if "listitem" in types:
                inner = node.get("item")
                target = inner if isinstance(inner, dict) else node
                if isinstance(inner, str) and not node.get("url"):
                    target = dict(node, url=inner)
                found = _item(target, base_url, default_timezone)
            elif types & ARTICLE_TYPES:
                found = _item(node, base_url, default_timezone)
            else:
                continue
            if found is not None:
                items.append(found)
    return items


def _microdata_value(element) -> str | None:
    for attribute in ("content", "datetime", "href", "src"):
        value = element.get(attribute)
        if value:
            return value
    return " ".join("".join(element.itertext()).split()) or None


def _from_microdata(document, base_url: str, default_timezone: str) -> list[dict[str, Any]]:
    items = []
    for scope in document.xpath("//*[@itemscope][@itemtype]"):
        types = {_TYPE_TAIL.split(value)[-1].lower() for value in scope.get("itemtype").split()}
        if not types & ARTICLE_TYPES:
            continue
        props: dict[str, str] = {}
        for element in scope.xpath(".//*[@itemprop]"):
            # Skip properties that belong to a nested item (author, publisher).
            owner = element.getparent()
            while owner is not None and owner is not scope and owner.get("itemscope") is None:
                owner = owner.getparent()
            if owner is not scope:
                continue
            for name in element.get("itemprop").split():
                if name not in props:
                    value = _microdata_value(element)
                    if value:
                        props[name] = value
        found = _item(props, base_url, default_timezone)
        if found is not None:
            items.append(found)
    return items


def extract_structured_items(
    document, base_url: str, *, default_timezone: str = "UTC"
) -> list[dict[str, Any]]:
    """Return de-duplicated news items described by JSON-LD or microdata.

    The page itself (a ``WebPage`` whose URL is ``base_url``) is not an item.
    """
    if document is None:
        return []
    page = clean_url(base_url)
    seen = set()
    items = []
    for item in _from_json_ld(document, base_url, default_timezone) + _from_microdata(
        document, base_url, default_timezone
    ):
        if item["link"] in seen or item["link"] == page:
            continue
        seen.add(item["link"])
        items.append(item)
    return items


def merge_structured_dates(items: list[dict[str, Any]], structured: list[dict[str, Any]]) -> int:
    """Fill or sharpen item dates and authors from structured data, by link.

    A structured date replaces a heuristic one when the heuristic item has no
    date, or when both fall on the same calendar day and the structured value
    carries a time of day. Returns the number of items changed.
    """
    by_link = {item["link"]: item for item in structured}
    changed = 0
    for item in items:
        match = by_link.get(item.get("link"))
        if match is None:
            continue
        updated = False
        exact = match.get("pubdate")
        current = item.get("pubdate")
        if isinstance(exact, dt.datetime):
            if current is None or (
                isinstance(current, dt.datetime)
                and current.date() == exact.date()
                and current.time() == dt.time(0)
                and exact.time() != dt.time(0)
            ):
                item["pubdate"] = exact
                updated = True
        if match.get("author") and not item.get("author"):
            item["author"] = match["author"]
            updated = True
        changed += updated
    return changed
