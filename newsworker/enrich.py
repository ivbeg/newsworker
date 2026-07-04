#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Per-item enrichment: author, categories and optional full-article text.

These helpers operate on an item's ``raw_html`` fragment (populated by both the
dynamic extractor and the spec extractor), so enrichment works uniformly across
extraction paths. All functions degrade gracefully: malformed HTML or a missing
optional dependency yields ``None``/empty rather than raising.
"""

import logging

from lxml.html import fromstring

log = logging.getLogger(__name__)


def _parse(html):
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
    metas = doc.xpath(
        "//meta[translate(@name,'AUTHOR','author')='author']/@content"
    )
    for meta in metas:
        if meta and meta.strip():
            return meta.strip()
    rel_nodes = doc.xpath(
        "//a[contains(concat(' ', normalize-space(@rel), ' '), ' author ')]"
    )
    for node in rel_nodes:
        text = node.text_content().strip()
        if text:
            return text
    class_nodes = doc.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' author ')]"
    )
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
    for node in doc.xpath(
        "//a[contains(concat(' ', normalize-space(@rel), ' '), ' tag ')]"
    ):
        text = node.text_content().strip()
        if text:
            categories.append(text)
    for cls in ("tags", "categories"):
        containers = doc.xpath(
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' %s ')]" % cls
        )
        for container in containers:
            links = container.xpath(".//a")
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


def enrich_item(item):
    """Adds ``author``/``categories`` to ``item`` from its ``raw_html`` in place."""
    html = item.get("raw_html")
    if not item.get("author"):
        author = extract_author(html)
        if author:
            item["author"] = author
    if not item.get("categories"):
        categories = extract_categories(html)
        if categories:
            item["categories"] = categories
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
    if not html:
        return None
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
        return text
    try:
        from readability import Document

        payload = html.decode("utf-8", "replace") if isinstance(html, bytes) else html
        return Document(payload).summary()
    except ImportError:
        return None
    except Exception as e:  # noqa: BLE001
        log.debug("readability extraction failed for %s: %s", url, e)
        return None
