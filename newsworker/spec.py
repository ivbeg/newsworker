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
from .tools import (
    clean_url,
    decode_html,
    get_abs_url,
    parse_datetime_attr,
    resolve_feed_language,
)

SPEC_VERSION = 1
HTML_TIME_PATTERN = "html:time"

# Container tags that hold UI controls, not news listings.
_FORM_CONTAINER_TAGS = frozenset({"select", "form", "option", "optgroup", "datalist"})

#: Heading tags preferred for item titles (h1 highest priority).
_HEADING_TAGS = ("h1", "h2", "h3", "h4")


def _element_text(node):
    """Returns visible text from an lxml element."""
    if node is None:
        return ""
    text_content = getattr(node, "text_content", None)
    if callable(text_content):
        return text_content()
    return "".join(node.itertext())


# ---------------------------------------------------------------------------
# Selector helpers
# ---------------------------------------------------------------------------


def _element_classes(node):
    """Returns the list of CSS classes for an lxml element."""
    value = node.get("class")
    return value.split() if value else []


# WordPress taxonomy / per-post classes are not reliable item markers.
_TAXONOMY_CLASS_PREFIXES = ("category-", "tag-")
_STRUCTURAL_ITEM_HINTS = ("item", "grid", "entry", "card", "post-grid")


def _is_taxonomy_class(cls):
    low = cls.lower()
    return any(low.startswith(prefix) for prefix in _TAXONOMY_CLASS_PREFIXES)


def _is_post_id_class(cls):
    if cls.startswith("post-") and cls[5:].isdigit():
        return True
    return False


def _item_selector_classes(classes):
    """Filters out taxonomy and per-post classes unsuitable for item selectors."""
    return [
        cls
        for cls in classes
        if not _is_taxonomy_class(cls) and not _is_post_id_class(cls)
    ]


def _pick_best_item_class(classes, prefer_keywords=None):
    """Picks the best shared class for a repeating news item wrapper."""
    candidates = _item_selector_classes(classes)
    if not candidates:
        return None
    best_cls = None
    best_score = (-1, -1)
    for cls in candidates:
        low = cls.lower()
        score = 0
        if prefer_keywords:
            for keyword in prefer_keywords:
                if keyword in low:
                    score = 100
                    break
        if score < 100:
            for hint in _STRUCTURAL_ITEM_HINTS:
                if hint in low:
                    score = 10
                    break
        rank = (score, len(cls))
        if rank > best_score:
            best_score = rank
            best_cls = cls
    return best_cls


def _shared_item_selector(item_roots, prefer_keywords=None):
    """Builds a CSS selector from classes shared by every item root."""
    if not item_roots:
        return None
    tag = getattr(item_roots[0], "tag", None)
    if not isinstance(tag, str):
        return None
    if any(getattr(root, "tag", None) != tag for root in item_roots[1:]):
        return None
    common = set(_element_classes(item_roots[0]))
    for root in item_roots[1:]:
        common &= set(_element_classes(root))
    cls = _pick_best_item_class(common, prefer_keywords)
    if cls:
        return "%s.%s" % (tag, cls)
    return None


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


def css_for_item_element(node, prefer_keywords=None):
    """Builds an item CSS selector, skipping taxonomy and post-id classes."""
    tag = getattr(node, "tag", None)
    if not isinstance(tag, str):
        return None
    cls = _pick_best_item_class(_element_classes(node), prefer_keywords)
    if cls:
        return "%s.%s" % (tag, cls)
    return tag


def _same_tag_index(node):
    """Returns the 1-based XPath index of ``node`` among same-tag siblings."""
    parent = node.getparent()
    if parent is None:
        return 1
    tag = node.tag if isinstance(node.tag, str) else "*"
    idx = 0
    for sibling in parent.iterchildren():
        if not isinstance(sibling.tag, str):
            continue
        if sibling.tag == tag:
            idx += 1
        if sibling is node:
            return idx or 1
    return 1


def relative_xpath(root, target):
    """Builds a positional XPath from ``root`` (exclusive) to ``target``."""
    parts = []
    node = target
    while node is not None and node is not root:
        parent = node.getparent()
        if parent is None:
            break
        tag = node.tag if isinstance(node.tag, str) else "*"
        parts.append("%s[%d]" % (tag, _same_tag_index(node)))
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
        parent = target.getparent()
        if parent is not None and parent is not item_root:
            parent_css = css_for_element(parent, prefer_keywords)
            if parent_css:
                compound = "%s %s" % (parent_css, css)
                try:
                    matches = item_root.cssselect(compound)
                except Exception:
                    matches = []
                if matches and matches[0] is target:
                    return compound
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
    source: str = "text"  # text | tail | content | attr:<name>
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


class SpecAnalysisError(Exception):
    """Raised when analysis cannot produce a usable parsing spec."""


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

    @staticmethod
    def _normalize_snode(snode):
        """Returns ``snode``, descending into ``tbody`` when it is a table."""
        if snode.tag == "table":
            for child in snode.getchildren():
                if child.tag == "tbody":
                    return child
        return snode

    def _map_item_roots(self, snode, nodes):
        """Maps date nodes under ``snode`` to their direct-child item roots."""
        item_roots = []
        date_by_root = {}
        for node_info in nodes:
            node = node_info["node"]
            root = self._item_root(snode, node)
            if root is None:
                continue
            if root not in date_by_root:
                item_roots.append(root)
                date_by_root[root] = node
        return item_roots, date_by_root

    def _cluster_score(self, cluster_info):
        """Scores a date cluster; higher is more likely to be a news listing."""
        snode = cluster_info["snode"]
        nodes = cluster_info["nodes"]
        if snode.tag in _FORM_CONTAINER_TAGS:
            return (-1, -1, -1, -1)
        option_dates = sum(
            1 for info in nodes if getattr(info["node"], "tag", None) == "option"
        )
        if option_dates and option_dates >= len(nodes) / 2:
            return (-1, -1, -1, -1)

        snode = self._normalize_snode(snode)
        item_roots, date_by_root = self._map_item_roots(snode, nodes)
        links = titles = 0
        for root in item_roots[:6]:
            fields = self._detect_fields(root, date_by_root.get(root))
            if fields["link"] is not None:
                links += 1
            if fields["title"][0] is not None:
                titles += 1

        news_bonus = 0
        for cls in _element_classes(snode):
            low = cls.lower()
            if any(keyword in low for keyword in NEWS_CLASSES_KEYWORDS):
                news_bonus = 1
                break
        return (links, titles, len(nodes), news_bonus)

    def _pick_best_cluster(self, clusters):
        """Returns the cluster most likely to contain repeating news items."""
        return max(clusters.items(), key=lambda kv: self._cluster_score(kv[1]))

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
        for tag in _HEADING_TAGS:
            for el in _walk_elements(item_root):
                if el is date_node:
                    continue
                if el.tag == tag:
                    text = _element_text(el).strip()
                    if len(text) > 10:
                        title, title_source = el, "content"
                        break
            if title is not None:
                break
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

    def _item_text_samples(self, item_roots, date_by_root, limit=12):
        """Returns title-like text snippets from discovered news items."""
        samples = []
        for root in item_roots[:limit]:
            fields = self._detect_fields(root, date_by_root[root])
            title_node, title_source = fields["title"]
            if title_node is None:
                continue
            if title_source == "tail":
                text = (title_node.tail or "").strip()
            elif title_source == "content":
                text = _element_text(title_node).strip()
            else:
                text = (title_node.text or "").strip()
            if not text:
                text = _element_text(title_node).strip()
            if len(text) >= 10:
                samples.append(text)
        return samples

    def _resolve_language(self, document, text_samples=None):
        return resolve_feed_language(
            override=getattr(self.ext, "default_language", None),
            document=document,
            content_language=getattr(self.ext, "_last_content_language", None),
            text_samples=text_samples,
        )

    def analyze(self, url, data=None, user_agent=None, require_items=False):
        """Analyzes ``url`` (or provided ``data``) and returns a ``FeedSpec``.

        When ``require_items`` is true, raises :class:`SpecAnalysisError` if the
        page does not contain a detectable news listing.
        """
        document = self._parse(url, data=data, user_agent=user_agent)
        spec = FeedSpec(
            source_url=url,
            analyzed_at=datetime.datetime.now().isoformat(timespec="seconds"),
            language=self._resolve_language(document),
        )
        if document is None:
            if require_items:
                raise SpecAnalysisError("Failed to fetch or parse page content")
            return spec
        spec.title = self._feed_title(document, url)

        self.ext.init_session()
        try:
            clusters = self.ext.getclusters(document, url)
        finally:
            self.ext.clear_session()

        if not clusters:
            if require_items:
                raise SpecAnalysisError("No dated news listings detected on this page")
            return spec

        best_path, best = self._pick_best_cluster(clusters)
        snode = self._normalize_snode(best["snode"])

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
            if require_items:
                raise SpecAnalysisError(
                    "Found date patterns but could not group them into individual news items"
                )
            return spec

        spec.language = self._resolve_language(
            document,
            text_samples=self._item_text_samples(item_roots, date_by_root),
        )

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
        if require_items:
            if not spec.fields:
                raise SpecAnalysisError(
                    "Could not derive extraction rules for news items on this page"
                )
            if "title" not in spec.fields and "link" not in spec.fields:
                raise SpecAnalysisError(
                    "Could not derive title or link extraction rules for news items on this page"
                )
            if not self._validate(document, spec):
                raise SpecAnalysisError(
                    "Built selectors matched fewer than 2 news items on this page"
                )
            if not self._validate_dates(document, spec):
                raise SpecAnalysisError(
                    "Built selectors could not parse dates from news items on this page"
                )
        return spec

    def _min_items_matched(self, item_count):
        """Minimum nodes a CSS item selector must match inside the container."""
        if item_count <= 2:
            return item_count
        return max(2, int(item_count * 0.9 + 0.999))

    def _css_items_rule(self, document, snode, item_roots, selector):
        container = document.getroottree().getpath(snode)
        try:
            matched = snode.cssselect(selector)
        except Exception:
            matched = []
        min_needed = self._min_items_matched(len(item_roots))
        if len(matched) >= min_needed and self._selector_specific_enough(
            selector, len(matched), len(item_roots)
        ):
            return ItemsRule(
                selector=selector,
                selector_type="css",
                container=container,
                stride=1,
            )
        return None

    def _build_items_rule(self, document, snode, item_roots):
        shared = _shared_item_selector(item_roots, NEWS_CLASSES_KEYWORDS)
        if shared:
            rule = self._css_items_rule(document, snode, item_roots, shared)
            if rule is not None:
                return rule

        counts = {}
        for root in item_roots:
            css = css_for_item_element(root, NEWS_CLASSES_KEYWORDS)
            if css:
                counts[css] = counts.get(css, 0) + 1
        if counts:
            selector = max(counts.items(), key=lambda kv: kv[1])[0]
            rule = self._css_items_rule(document, snode, item_roots, selector)
            if rule is not None:
                return rule
        return self._positional_items_rule(document, snode, item_roots)

    @staticmethod
    def _selector_specific_enough(selector, matched_count, item_count):
        """Returns whether a CSS item selector is precise enough to use.

        Bare tag selectors (``div``, ``tr``, …) and selectors that match far
        more nodes than discovered news items are rejected in favour of a
        positional fallback.
        """
        if item_count <= 0:
            return False
        if "." not in selector:
            return matched_count <= item_count * 1.1
        if matched_count <= item_count * 1.1:
            return True
        # Date clustering can miss an item; allow a small overshoot for
        # specific class selectors.
        return matched_count <= item_count + 1

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
            if patterns and HTML_TIME_PATTERN in patterns:
                if (
                    isinstance(getattr(date_node, "tag", None), str)
                    and date_node.tag == "time"
                    and date_node.get("datetime")
                ):
                    date_source = "attr:datetime"
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

    def _validate_dates(self, document, spec):
        """Returns whether at least one item scope yields a parseable date."""
        date_rule = spec.fields.get("date")
        if date_rule is None:
            return True
        try:
            scopes = _select_item_scopes(document, spec.items)
        except Exception:
            return False
        for scope in scopes[:3]:
            _, pubdate = extract_date_from_scope(
                self.ext, scope, date_rule, date_rule.patterns
            )
            if pubdate is not None:
                return True
        return False


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
    if source == "content":
        return _element_text(node)
    if source.startswith("attr:"):
        return node.get(source[len("attr:") :])
    return node.text


def _qddate_patterns(patterns):
    """Returns qddate pattern keys, dropping the non-regex ``html:time`` marker."""
    if not patterns:
        return None
    filtered = [p for p in patterns if p != HTML_TIME_PATTERN]
    return filtered or None


def _date_target_nodes(scope, date_rule):
    nodes = []
    for node in scope:
        nodes.extend(select_nodes(node, date_rule.selector))
    return nodes


def extract_date_from_scope(ext, scope, date_rule, patterns):
    """Extracts ``(date_text, pubdate)`` from an item scope.

    ``html:time`` patterns are resolved via :meth:`FeedExtractor.match_date`
    (or ``datetime`` attributes) rather than qddate text matching alone.
    """
    if date_rule is None:
        return None, None

    use_html_time = patterns and HTML_TIME_PATTERN in patterns
    if use_html_time:
        for node in _date_target_nodes(scope, date_rule):
            matched, _key, _data, matched_text, the_date = ext.match_date(node)
            if matched:
                return matched_text, the_date

    date_text = _extract_value(scope, date_rule)
    if date_text:
        if date_rule.source == "attr:datetime" or use_html_time:
            the_date = parse_datetime_attr(date_text)
            if the_date is not None:
                return date_text, the_date

    the_date = _parse_date_text(ext, date_text, _qddate_patterns(patterns))
    return date_text, the_date


def _parse_date_text(ext, text, patterns):
    if not text:
        return None
    if patterns:
        ext.indexer.startSession(patterns)
    try:
        match, _key, _data, _matched_text, the_date = ext.match_text(text)
    finally:
        if patterns:
            ext.indexer.endSession()
    if match:
        return the_date
    return None


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
        if not getattr(self.ext, "default_language", None):
            samples = [
                item.get("title") for item in feed["items"] if item.get("title")
            ]
            feed["language"] = resolve_feed_language(
                document=document,
                content_language=getattr(self.ext, "_last_content_language", None),
                stored_language=spec.language,
                text_samples=samples,
            )
        return feed

    def _extract_item(self, base_url, scope, spec, date_rule, patterns):
        date_text = None
        pubdate = None
        if date_rule is not None:
            date_text, pubdate = extract_date_from_scope(
                self.ext, scope, date_rule, patterns
            )
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
