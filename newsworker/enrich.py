#!/usr/bin/env python
"""Per-item enrichment: author, categories and optional full-article text.

These helpers operate on an item's ``raw_html`` fragment (populated by both the
dynamic extractor and the spec extractor), so enrichment works uniformly across
extraction paths. All functions degrade gracefully: malformed HTML or a missing
optional dependency yields ``None``/empty rather than raising.
"""

import logging
from typing import Any

from lxml import etree
from lxml.html import fromstring

from .tools import compiled_xpath

log = logging.getLogger(__name__)

# XPath expressions run on every item; compiled once per thread
# (:func:`newsworker.tools.compiled_xpath`).
_AUTHOR_META = "//meta[translate(@name,'AUTHOR','author')='author']/@content"
_AUTHOR_REL = "//a[contains(concat(' ', normalize-space(@rel), ' '), ' author ')]"
_AUTHOR_CLASS = "//*[contains(concat(' ', normalize-space(@class), ' '), ' author ')]"
_TAG_REL = "//a[contains(concat(' ', normalize-space(@rel), ' '), ' tag ')]"
_CLASS_CONTAINER = "//*[contains(concat(' ', normalize-space(@class), ' '), ' %s ')]"
_ENCLOSURES = ".//a[contains(concat(' ', normalize-space(@rel), ' '), ' enclosure ')] | .//img"


def _parse(html):
    """``html`` parsed; an element already parsed is returned as it is."""
    if html is None or isinstance(html, etree._Element):
        return html
    if not html:
        return None
    try:
        return fromstring(html)
    except Exception:  # noqa: BLE001 - lxml raises assorted parse errors
        return None


def extract_author(html):
    """Returns an author string discovered in ``html`` fragment, or ``None``.

    Looks at ``<meta name=author>``, ``rel="author"`` links and ``.author``
    elements, in that order.
    """
    doc = _parse(html)
    if doc is None:
        return None
    metas = compiled_xpath(_AUTHOR_META)(doc)
    for meta in metas:
        if meta and meta.strip():
            return meta.strip()
    rel_nodes = compiled_xpath(_AUTHOR_REL)(doc)
    for node in rel_nodes:
        text = node.text_content().strip()
        if text:
            return text
    class_nodes = compiled_xpath(_AUTHOR_CLASS)(doc)
    for node in class_nodes:
        text = node.text_content().strip()
        if text:
            return text
    return None


def extract_categories(html):
    """Returns a de-duplicated list of category/tag labels from ``html``."""
    doc = _parse(html)
    if doc is None:
        return []
    categories = []
    for node in compiled_xpath(_TAG_REL)(doc):
        text = node.text_content().strip()
        if text:
            categories.append(text)
    for cls in ("tags", "categories"):
        containers = compiled_xpath(_CLASS_CONTAINER % cls)(doc)
        for container in containers:
            links = compiled_xpath(".//a")(container)
            if links:
                for link in links:
                    text = link.text_content().strip()
                    if text:
                        categories.append(text)
            else:
                text = container.text_content().strip()
                if text:
                    categories.append(text)
    seen = set()
    unique = []
    for category in categories:
        if category not in seen:
            seen.add(category)
            unique.append(category)
    return unique


def extract_enclosure_metadata(html):
    """Return truthful ``(media_type, length)`` metadata present in item HTML.

    The listing document itself is fetched through the bounded source policy. We
    accept only explicit metadata on an enclosure link or image and never infer a
    media type from a filename or fabricate a byte length.
    """
    doc = _parse(html)
    if doc is None:
        return None, None
    nodes = compiled_xpath(_ENCLOSURES)(doc)
    for node in nodes:
        media_type = node.get("type") or node.get("data-media-type")
        raw_length = (
            node.get("length")
            or node.get("data-length")
            or node.get("data-size")
            or node.get("filesize")
        )
        try:
            length = int(raw_length) if raw_length is not None else None
        except (TypeError, ValueError):
            length = None
        if media_type and length is not None and length >= 0:
            return media_type.strip().lower(), length
    return None, None


def enrich_item(item):
    """Adds ``author``/``categories`` to ``item`` from its ``raw_html`` in place."""
    raw_html = item.get("raw_html")
    parsed: list[Any] = []

    def html():
        # Parsed once, on first use, for all three lookups.
        if not parsed:
            parsed.append(_parse(raw_html))
        return parsed[0]

    if not item.get("author"):
        author = extract_author(html())
        if author:
            item["author"] = author
    if not item.get("categories"):
        categories = extract_categories(html())
        if categories:
            item["categories"] = categories
    extra = item.get("extra")
    if not isinstance(extra, dict):
        extra = {}
        item["extra"] = extra
    if extra.get("images") and not (
        extra.get("enclosure_type") and extra.get("enclosure_length") is not None
    ):
        media_type, length = extract_enclosure_metadata(html())
        if media_type and length is not None:
            extra["enclosure_type"] = media_type
            extra["enclosure_length"] = length
    return item


def enrich_feed(feed):
    """Enriches every item of ``feed`` in place and returns ``feed``."""
    for item in feed.get("items", []):
        enrich_item(item)
    return feed


def extract_fulltext(html, url=None):
    """Returns the main article text from ``html`` or ``None``.

    Prefers ``trafilatura``; falls back to ``readability-lxml``. Returns ``None``
    when neither optional dependency is installed or extraction fails.
    """
    return extract_fulltext_with_kind(html, url=url)[0]


def extract_fulltext_with_kind(html, url=None):
    """Like :func:`extract_fulltext` but also reports ``"text"`` or ``"html"``.

    trafilatura yields plain text; the readability fallback yields an HTML
    fragment, which must not be labelled as text downstream.
    """
    text, kind = _extract_fulltext(html, url)
    return text, (kind if text else None)


def _extract_fulltext(html, url):
    if not html:
        return None, None
    text = None
    try:
        import trafilatura

        payload = html.decode("utf-8", "replace") if isinstance(html, bytes) else html
        text = trafilatura.extract(payload, url=url)
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001
        log.debug("trafilatura extraction failed for %s: %s", url, e)
    if text:
        return text, "text"
    try:
        from readability import Document

        payload = html.decode("utf-8", "replace") if isinstance(html, bytes) else html
        return Document(payload).summary(), "html"
    except ImportError:
        return None, None
    except Exception as e:  # noqa: BLE001
        log.debug("readability extraction failed for %s: %s", url, e)
        return None, None
