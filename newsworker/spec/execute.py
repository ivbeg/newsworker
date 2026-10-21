"""Applying a :class:`FeedSpec` to a page: deterministic selectors, no heuristics."""

import hashlib

from lxml import etree
from lxml.html import fromstring

from ..extractor import FeedExtractor
from ..tools import clean_url, decode_html, get_abs_url, parse_datetime_attr, resolve_feed_language
from .model import HTML_TIME_PATTERN
from .selectors import _element_text, select_nodes

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
    if getattr(items_rule, "group", None) == "siblings":
        return _sibling_groups(nodes)
    stride = items_rule.stride or 1
    if stride <= 1:
        return [[n] for n in nodes]
    scopes = []
    for i in range(0, len(nodes), stride):
        scopes.append(nodes[i : i + stride])
    return scopes


def _sibling_groups(starts):
    """Each start node plus its following siblings, up to the next start node."""
    markers = {id(node) for node in starts}
    scopes = []
    for node in starts:
        scope = [node]
        sibling = node.getnext()
        while sibling is not None and id(sibling) not in markers:
            if isinstance(sibling.tag, str):
                scope.append(sibling)
            sibling = sibling.getnext()
        scopes.append(scope)
    return scopes


def _extract_value(scope, rule):
    """Extracts a raw string value for a field rule from an item scope."""
    for node in scope:
        targets = select_nodes(node, rule.selector)
        for target in targets:
            value = _read_source(target, rule.source)
            value = value.strip() if value else value
            if value:
                return value
    return None


#: Shorthand field sources accepted by the schema and their attribute names.
SOURCE_ALIASES = {"href": "attr:href", "src": "attr:src", "datetime": "attr:datetime"}


def _read_source(node, source):
    source = SOURCE_ALIASES.get(source, source)
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
    if date_text and (date_rule.source == "attr:datetime" or use_html_time):
        the_date = parse_datetime_attr(date_text)
        if the_date is not None:
            return date_text, the_date

    the_date = _parse_date_text(ext, date_text, _qddate_patterns(patterns))
    return date_text, the_date


def _parse_date_text(ext, text, patterns):
    if not text:
        return None
    with ext.narrowed_dates(list(patterns) if patterns else None):
        match, _key, _data, _matched_text, the_date = ext.match_text(text)
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

    def extract(self, url, spec, data=None, user_agent=None, context=None):
        if context is None:
            return self._extract_active(url, spec, data=data, user_agent=user_agent)
        with self.ext.activate_context(context):
            return self._extract_active(url, spec, data=data, user_agent=user_agent)

    def _extract_active(self, url, spec, data=None, user_agent=None):
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
        self.ext.use_page_language(document)

        date_rule = spec.fields.get("date")
        patterns = date_rule.patterns if date_rule else None

        for scope in _select_item_scopes(document, spec.items):
            if not scope:
                continue
            item = self._extract_item(url, scope, spec, date_rule, patterns)
            if item is not None:
                feed["items"].append(item)
        override = getattr(self.ext, "default_language", None)
        if override:
            feed["language"] = resolve_feed_language(override=override)
        else:
            samples = [item.get("title") for item in feed["items"] if item.get("title")]
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
            date_text, pubdate = extract_date_from_scope(self.ext, scope, date_rule, patterns)
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

        raw_html = b"".join(etree.tostring(node, encoding="utf8") for node in scope)

        md = hashlib.md5(usedforsecurity=False)
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
