#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Parsing specification (spec) support for newsworker.

A spec captures, in a serializable (YAML) form, how to extract a news feed from
a given site layout: how to locate the repeating news items and how to pull the
individual fields (date, title, link, description, image) out of each item.

Two entry points are provided:

* :class:`SpecAnalyzer` runs the existing dynamic date-driven heuristics once and
  distills them into a :class:`FeedSpec`.
* :class:`SpecExtractor` applies a :class:`FeedSpec` to a page, which is much
  faster than the dynamic pipeline because it uses deterministic selectors and
  restricts date parsing to only the patterns discovered during analysis.

Selector convention
--------------------
Every selector string is interpreted as follows:

* empty string ``""`` -> the item element itself;
* a string starting with ``.`` or ``/`` -> an XPath expression;
* anything else -> a CSS selector (via ``lxml``'s ``cssselect``).

This keeps the YAML readable while allowing a semantic-first strategy with a
positional XPath fallback.
"""

import datetime
import hashlib
from dataclasses import dataclass, field
from typing import List, Optional

import yaml
from lxml import etree
from lxml.html import fromstring

from .consts import DATE_CLASSES_KEYWORDS, NEWS_CLASSES_KEYWORDS
from .extractor import FeedExtractor
from .tools import clean_url, decode_html, get_abs_url

SPEC_VERSION = 1


# ---------------------------------------------------------------------------
# Selector helpers
# ---------------------------------------------------------------------------


def _element_classes(node):
    """Returns the list of CSS classes for an lxml element."""
    value = node.get("class")
    return value.split() if value else []


def _best_class(node, prefer_keywords=None):
    """Picks the most useful class for a node.

    When ``prefer_keywords`` is provided, a class whose name contains one of the
    keywords is preferred (this leverages the NEWS/DATE class keyword lists).
    """
    classes = _element_classes(node)
    if not classes:
        return None
    if prefer_keywords:
        for cls in classes:
            low = cls.lower()
            for keyword in prefer_keywords:
                if keyword in low:
                    return cls
    return classes[0]


def css_for_element(node, prefer_keywords=None):
    """Builds a ``tag`` or ``tag.class`` CSS selector for a single element."""
    tag = getattr(node, "tag", None)
    if not isinstance(tag, str):
        return None
    cls = _best_class(node, prefer_keywords)
    if cls:
        return "%s.%s" % (tag, cls)
    return tag


def relative_xpath(root, target):
    """Builds a positional XPath from ``root`` (exclusive) to ``target``."""
    parts = []
    node = target
    while node is not None and node is not root:
        parent = node.getparent()
        if parent is None:
            break
        try:
            idx = parent.index(node) + 1
        except (ValueError, TypeError):
            idx = 1
        tag = node.tag if isinstance(node.tag, str) else "*"
        parts.append("%s[%d]" % (tag, idx))
        node = parent
    if not parts:
        return "."
    parts.reverse()
    return "./" + "/".join(parts)


def relative_selector(item_root, target, prefer_keywords=None):
    """Returns a selector from ``item_root`` to ``target``.

    Prefers a semantic ``tag.class`` CSS selector when it uniquely (first-match)
    resolves to ``target``; otherwise falls back to a positional relative XPath.
    """
    if target is item_root:
        return ""
    css = css_for_element(target, prefer_keywords)
    if css:
        try:
            matches = item_root.cssselect(css)
        except Exception:
            matches = []
        if matches and matches[0] is target:
            return css
    return relative_xpath(item_root, target)


def _is_xpath(selector):
    return selector.startswith(".") or selector.startswith("/")


def select_nodes(scope, selector):
    """Selects nodes under ``scope`` using the selector convention.

    Empty selector resolves to ``[scope]`` (the element itself).
    """
    if selector == "":
        return [scope]
    if _is_xpath(selector):
        try:
            return scope.xpath(selector)
        except Exception:
            return []
    try:
        return scope.cssselect(selector)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Spec data structures
# ---------------------------------------------------------------------------


@dataclass
class FieldRule:
    """Rule describing how to extract a single field from an item element."""

    selector: str = ""
    source: str = "text"  # text | tail | attr:<name>
    absolute: bool = False  # resolve value as an absolute URL
    patterns: Optional[List[str]] = None  # qddate pattern keys (date field only)
    required: bool = False

    def to_dict(self):
        data = {"selector": self.selector, "source": self.source}
        if self.absolute:
            data["absolute"] = True
        if self.patterns is not None:
            data["patterns"] = list(self.patterns)
        if self.required:
            data["required"] = True
        return data

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return None
        return cls(
            selector=data.get("selector", ""),
            source=data.get("source", "text"),
            absolute=bool(data.get("absolute", False)),
            patterns=data.get("patterns"),
            required=bool(data.get("required", False)),
        )


@dataclass
class ItemsRule:
    """Rule describing how to locate repeating news item elements."""

    selector: str = "./*"
    selector_type: str = "css"  # css | xpath (informational; auto-detected too)
    container: Optional[str] = None
    stride: int = 1

    def to_dict(self):
        data = {
            "selector_type": self.selector_type,
            "selector": self.selector,
        }
        if self.container:
            data["container"] = self.container
        if self.stride and self.stride != 1:
            data["stride"] = self.stride
        return data

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            selector=data.get("selector", "./*"),
            selector_type=data.get("selector_type", "css"),
            container=data.get("container"),
            stride=int(data.get("stride", 1) or 1),
        )


@dataclass
class FeedSpec:
    """Full serializable parsing specification for a site layout."""

    source_url: Optional[str] = None
    analyzed_at: Optional[str] = None
    title: Optional[str] = None
    language: str = "en"
    items: ItemsRule = field(default_factory=ItemsRule)
    fields: dict = field(default_factory=dict)  # name -> FieldRule
    version: int = SPEC_VERSION

    def to_dict(self):
        return {
            "version": self.version,
            "source": {
                "url": self.source_url,
                "analyzed_at": self.analyzed_at,
            },
            "feed": {
                "title": self.title,
                "language": self.language,
            },
            "items": self.items.to_dict(),
            "fields": {
                name: rule.to_dict() for name, rule in self.fields.items()
            },
        }

    def to_yaml(self):
        return yaml.safe_dump(
            self.to_dict(), sort_keys=False, allow_unicode=True, default_flow_style=False
        )

    @classmethod
    def from_dict(cls, data):
        source = data.get("source", {}) or {}
        feed = data.get("feed", {}) or {}
        fields = {}
        for name, raw in (data.get("fields", {}) or {}).items():
            rule = FieldRule.from_dict(raw)
            if rule is not None:
                fields[name] = rule
        return cls(
            source_url=source.get("url"),
            analyzed_at=source.get("analyzed_at"),
            title=feed.get("title"),
            language=feed.get("language", "en"),
            items=ItemsRule.from_dict(data.get("items")),
            fields=fields,
            version=int(data.get("version", SPEC_VERSION)),
        )

    @classmethod
    def from_yaml(cls, text):
        return cls.from_dict(yaml.safe_load(text) or {})

    def save(self, path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.to_yaml())

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_yaml(handle.read())


# ---------------------------------------------------------------------------
# Analysis: HTML -> FeedSpec
# ---------------------------------------------------------------------------


def _walk_elements(node):
    """Yields ``node`` and all descendant elements in document order."""
    yield node
    for child in node.iterchildren():
        if not isinstance(child.tag, str):
            continue
        yield from _walk_elements(child)


class SpecAnalyzer:
    """Derives a :class:`FeedSpec` from a page using the dynamic heuristics."""

    def __init__(self, extractor=None, filtered_text_length=150):
        self.ext = extractor or FeedExtractor(filtered_text_length=filtered_text_length)

    def _parse(self, url, data=None, user_agent=None):
        if data is None:
            data = self.ext.fetch(url, user_agent)
        edata = decode_html(data)
        parser = etree.HTMLParser(remove_blank_text=True)
        return fromstring(edata, parser=parser)

    def _item_root(self, snode, node):
        """Returns the direct child of ``snode`` that contains ``node``."""
        current = node
        while current is not None and current.getparent() is not snode:
            current = current.getparent()
        return current

    def _feed_title(self, document, url):
        nodes = document.xpath("//head/title")
        if nodes and nodes[0].text:
            return nodes[0].text.strip()
        return "News from " + url

    def _detect_fields(self, item_root, date_node):
        """Picks representative field nodes inside an item using tag heuristics."""
        title = None
        title_source = None
        description = None
        description_source = None
        link = None
        image = None
        for el in _walk_elements(item_root):
            if el is date_node:
                continue
            text = el.text.strip() if el.text else ""
            if len(text) > 10:
                if title is None:
                    title, title_source = el, "text"
                elif description is None:
                    description, description_source = el, "text"
            tail = el.tail.strip() if el.tail else ""
            if len(tail) > 10:
                if title is None:
                    title, title_source = el, "tail"
                elif description is None:
                    description, description_source = el, "tail"
            if el.tag == "a" and "href" in el.attrib and link is None:
                link = el
            if el.tag == "img" and "src" in el.attrib and image is None:
                image = el
        return {
            "title": (title, title_source),
            "description": (description, description_source),
            "link": link,
            "image": image,
        }

    def analyze(self, url, data=None, user_agent=None):
        """Analyzes ``url`` (or provided ``data``) and returns a ``FeedSpec``."""
        document = self._parse(url, data=data, user_agent=user_agent)
        spec = FeedSpec(
            source_url=url,
            analyzed_at=datetime.datetime.now().isoformat(timespec="seconds"),
            language="en",
        )
        if document is None:
            return spec
        spec.title = self._feed_title(document, url)

        self.ext.init_session()
        try:
            clusters = self.ext.getclusters(document, url)
        finally:
            self.ext.clear_session()

        if not clusters:
            return spec

        # Pick the cluster with the most date-bearing nodes.
        best_path, best = max(
            clusters.items(), key=lambda kv: len(kv[1]["nodes"])
        )
        snode = best["snode"]
        if snode.tag == "table":
            for child in snode.getchildren():
                if child.tag == "tbody":
                    snode = child
                    break

        # Map every date node to its item root (direct child of snode).
        item_roots = []
        date_by_root = {}
        patterns = []
        for node_info in best["nodes"]:
            node = node_info["node"]
            t_key = node_info.get("t_key")
            if t_key and t_key not in patterns:
                patterns.append(t_key)
            root = self._item_root(snode, node)
            if root is None:
                continue
            if root not in date_by_root:
                item_roots.append(root)
                date_by_root[root] = node

        if not item_roots:
            return spec

        # Item selector: prefer a semantic tag.class shared by item roots.
        spec.items = self._build_items_rule(document, snode, item_roots)

        # Field rules: use the first item root that has a usable date + text.
        spec.fields = self._build_field_rules(item_roots, date_by_root, patterns)

        # Validate against the same document; fall back to positional if empty.
        if not self._validate(document, spec):
            spec.items = self._positional_items_rule(document, snode, item_roots)
            if not self._validate(document, spec):
                # Keep the semantic attempt; extraction may still work partially.
                pass
        return spec

    def _build_items_rule(self, document, snode, item_roots):
        counts = {}
        for root in item_roots:
            css = css_for_element(root, NEWS_CLASSES_KEYWORDS)
            if css:
                counts[css] = counts.get(css, 0) + 1
        container = document.getroottree().getpath(snode)
        if counts:
            selector = max(counts.items(), key=lambda kv: kv[1])[0]
            try:
                matched = snode.cssselect(selector)
            except Exception:
                matched = []
            if len(matched) >= max(2, int(len(item_roots) * 0.6)):
                return ItemsRule(
                    selector=selector,
                    selector_type="css",
                    container=container,
                    stride=1,
                )
        return self._positional_items_rule(document, snode, item_roots)

    def _positional_items_rule(self, document, snode, item_roots):
        container = document.getroottree().getpath(snode)
        stride = self._infer_stride(snode, item_roots)
        return ItemsRule(
            selector="./*",
            selector_type="xpath",
            container=container,
            stride=stride,
        )

    def _infer_stride(self, snode, item_roots):
        indices = []
        for root in item_roots:
            try:
                indices.append(snode.index(root))
            except (ValueError, TypeError):
                continue
        indices.sort()
        gaps = {}
        for i in range(1, len(indices)):
            diff = indices[i] - indices[i - 1]
            if diff > 0:
                gaps[diff] = gaps.get(diff, 0) + 1
        if not gaps:
            return 1
        return max(gaps.items(), key=lambda kv: kv[1])[0]

    def _build_field_rules(self, item_roots, date_by_root, patterns):
        fields = {}
        sample_root = None
        for root in item_roots:
            if date_by_root.get(root) is not None:
                sample_root = root
                break
        if sample_root is None:
            sample_root = item_roots[0]
        date_node = date_by_root.get(sample_root)

        # Date rule.
        if date_node is not None:
            date_source = "text"
            if not (date_node.text and date_node.text.strip()):
                date_source = "tail"
            fields["date"] = FieldRule(
                selector=relative_selector(
                    sample_root, date_node, DATE_CLASSES_KEYWORDS
                ),
                source=date_source,
                patterns=patterns or None,
                required=True,
            )

        detected = self._detect_fields(sample_root, date_node)

        title_node, title_source = detected["title"]
        if title_node is not None:
            fields["title"] = FieldRule(
                selector=relative_selector(sample_root, title_node),
                source=title_source,
            )

        desc_node, desc_source = detected["description"]
        if desc_node is not None:
            fields["description"] = FieldRule(
                selector=relative_selector(sample_root, desc_node),
                source=desc_source,
            )

        link_node = detected["link"]
        if link_node is not None:
            fields["link"] = FieldRule(
                selector=relative_selector(sample_root, link_node),
                source="attr:href",
                absolute=True,
            )

        image_node = detected["image"]
        if image_node is not None:
            fields["image"] = FieldRule(
                selector=relative_selector(sample_root, image_node),
                source="attr:src",
                absolute=True,
            )
        return fields

    def _validate(self, document, spec):
        try:
            scopes = _select_item_scopes(document, spec.items)
        except Exception:
            return False
        return len(scopes) >= 2


# ---------------------------------------------------------------------------
# Extraction: FeedSpec -> feed dict
# ---------------------------------------------------------------------------


def _select_item_scopes(document, items_rule):
    """Returns a list of item scopes; each scope is a list of element nodes."""
    scope_root = document
    if items_rule.container:
        containers = select_nodes(document, items_rule.container)
        if not containers:
            return []
        scope_root = containers[0]
    nodes = select_nodes(scope_root, items_rule.selector)
    nodes = [n for n in nodes if isinstance(getattr(n, "tag", None), str)]
    stride = items_rule.stride or 1
    if stride <= 1:
        return [[n] for n in nodes]
    scopes = []
    for i in range(0, len(nodes), stride):
        scopes.append(nodes[i : i + stride])
    return scopes


def _extract_value(scope, rule):
    """Extracts a raw string value for a field rule from an item scope."""
    for node in scope:
        targets = select_nodes(node, rule.selector)
        for target in targets:
            value = _read_source(target, rule.source)
            if value:
                return value.strip()
    return None


def _read_source(node, source):
    if source == "text":
        return node.text
    if source == "tail":
        return node.tail
    if source.startswith("attr:"):
        return node.get(source[len("attr:") :])
    return node.text


class SpecExtractor:
    """Applies a :class:`FeedSpec` to a page and returns a feed dict."""

    def __init__(self, extractor=None):
        self.ext = extractor or FeedExtractor()

    def _parse(self, url, data=None, user_agent=None):
        if data is None:
            data = self.ext.fetch(url, user_agent)
        edata = decode_html(data)
        parser = etree.HTMLParser(remove_blank_text=True)
        return fromstring(edata, parser=parser)

    def _parse_date(self, text, patterns):
        if not text:
            return None
        if patterns:
            self.ext.indexer.startSession(patterns)
        try:
            match, key, data, matched_text, the_date = self.ext.match_text(text)
        finally:
            if patterns:
                self.ext.indexer.endSession()
        if match:
            return the_date
        return None

    def extract(self, url, spec, data=None, user_agent=None):
        """Extracts a feed from ``url`` using ``spec``."""
        document = self._parse(url, data=data, user_agent=user_agent)
        feed = {
            "title": spec.title or ("News from " + url),
            "language": spec.language or "en",
            "link": url,
            "description": spec.title or ("News from " + url),
            "items": [],
        }
        if document is None:
            return feed

        date_rule = spec.fields.get("date")
        patterns = date_rule.patterns if date_rule else None

        for scope in _select_item_scopes(document, spec.items):
            if not scope:
                continue
            item = self._extract_item(url, scope, spec, date_rule, patterns)
            if item is not None:
                feed["items"].append(item)
        return feed

    def _extract_item(self, base_url, scope, spec, date_rule, patterns):
        pubdate = None
        date_text = None
        if date_rule is not None:
            date_text = _extract_value(scope, date_rule)
            pubdate = self._parse_date(date_text, patterns)
            if date_rule.required and pubdate is None:
                return None

        title = self._field(scope, spec.fields.get("title"), base_url)
        description = self._field(scope, spec.fields.get("description"), base_url)
        link = self._field(scope, spec.fields.get("link"), base_url)
        image = self._field(scope, spec.fields.get("image"), base_url)

        if title is None and description is None and pubdate is None:
            return None
        if description is None and title is not None:
            description = title

        raw_html = b"".join(
            etree.tostring(node, encoding="utf8") for node in scope
        )

        md = hashlib.md5()
        for part in (date_text, title, description, link):
            if part:
                md.update(part.encode("utf8"))

        item = {
            "title": title,
            "description": description,
            "pubdate": pubdate,
            "unique_id": md.hexdigest(),
            "raw_html": raw_html,
            "link": link or clean_url(base_url),
        }
        item["extra"] = {
            "links": [link] if link else [],
            "images": [image] if image else [],
        }
        return item

    def _field(self, scope, rule, base_url):
        if rule is None:
            return None
        value = _extract_value(scope, rule)
        if value is None:
            return None
        if rule.absolute:
            return clean_url(get_abs_url(base_url, value))
        return value
