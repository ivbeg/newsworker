#!/usr/bin/env python
"""Dynamic, date-driven news extraction from HTML pages (the original algorithm)."""

import contextvars
import hashlib
import threading
from copy import copy
from dataclasses import replace
from typing import Any

from lxml import etree
from lxml.html import fromstring
from urllib3.util.retry import Retry

from .consts import (
    TAG_TYPE_BOLD,
    TAG_TYPE_DATE,
    TAG_TYPE_HREF,
    TAG_TYPE_IMG,
    TAG_TYPE_TAIL,
    TAG_TYPE_TEXT,
)
from .dates import (
    DAY,
    DateReading,
    anchor_day,
    build_match_datetime,
    choose_date_order,
    date_text_variants,
    has_letters,
    is_ambiguous,
    match_precision,
    numeric_order,
    qddate_language,
    read_datetime_attr,
)
from .fetch import FetchPolicy, FetchRequest, FetchResult, RequestsTransport, new_session
from .relative import read_relative
from .runtime import ExtractionContext
from .tagmapper import TagBlock, TagPath
from .tools import (
    Logger,
    clean_url,
    decode_html,
    detect_page_locale,
    get_abs_url,
    looks_like_fuzzy_date,
    normalize_language_tag,
    pick_link_node,
    resolve_feed_language,
    validate_url,
)

#: Heading tags checked for titles before generic long-text heuristics.
_HEADING_TAGS = ("h1", "h2", "h3", "h4")


def _element_text(node):
    """Returns visible text from an lxml element."""
    if node is None:
        return ""
    text_content = getattr(node, "text_content", None)
    if callable(text_content):
        return text_content()
    return "".join(node.itertext())


# Default timeout for HTTP requests
DEFAULT_TIMEOUT = 30

#: Default cap on fetched response size (bytes). Guards against very large or
#: hostile pages exhausting memory. Override via ``FeedExtractor(max_bytes=...)``.
DEFAULT_MAX_BYTES = 10 * 1024 * 1024


class FeedExtractor:
    """Feed Extraction class"""

    def __init__(
        self,
        debug=True,
        patterns=None,
        filtered_text_length=150,
        max_bytes=DEFAULT_MAX_BYTES,
        verify_tls=True,
        respect_robots=True,
        timeout=DEFAULT_TIMEOUT,
        proxy=None,
        extra_headers=None,
        cookies_file=None,
        default_language=None,
    ):
        """

        :param patterns:List of patterns to use as rules
        :param verify_tls: verify TLS certificates on outgoing requests.
        :param respect_robots: consult ``robots.txt`` before fetching.
        :param timeout: seconds to wait for an HTTP response.
        :param proxy: optional proxy URL for outgoing requests.
        :param extra_headers: extra HTTP headers sent on every request.
        :param cookies_file: optional Netscape cookie jar path.
        """
        self._context_var = contextvars.ContextVar("newsworker_extraction_context", default=None)
        self._fallback_context = ExtractionContext()
        self.debug = debug
        self.log.save("initclass", "Date patterns will be loaded per request")
        # key parameters
        self.filtered_text_length = filtered_text_length
        self.max_bytes = max_bytes
        self.verify_tls = verify_tls
        self.respect_robots = respect_robots
        self.timeout = timeout
        self.proxy = proxy or None
        self.extra_headers = dict(extra_headers or {})
        self.cookies_file = cookies_file or None
        self._cookie_jar = None
        #: Explicit language override; empty/None means auto-detect.
        self.default_language = default_language or None
        self.default_timezone = "UTC"
        #: Address policy used when no ``base_policy`` is set (plain library use).
        self.redirect_limit = 5
        self.allowed_hosts: tuple = ()
        self.block_private_hosts = True
        self.allow_private_hosts = False
        self.trusted_proxy = False
        self.legacy_tls_ciphers = False
        #: Outbound policy from :func:`newsworker.fetch.policy_from_settings`;
        #: when unset (plain library use) it is assembled from the attributes above.
        self.base_policy: FetchPolicy | None = None
        # One pooled, address-guarded session per thread: concurrent fetches
        # (server requests, full-text workers) no longer queue behind a lock.
        self._http_sessions = threading.local()
        self.transport = RequestsTransport(session_factory=lambda: self.http_session)

    @property
    def http_session(self):
        """This thread's HTTP session (retries 429/5xx with backoff)."""
        session = getattr(self._http_sessions, "session", None)
        if session is None:
            # 429/Retry-After are left to the host scheduler, whose waits are
            # bounded; urllib3 would sleep for however long the server asks.
            session = new_session(
                Retry(
                    total=3,
                    backoff_factor=1,
                    status_forcelist=[500, 502, 503, 504],
                    respect_retry_after_header=False,
                )
            )
            self._http_sessions.session = session
        return session

    @http_session.setter
    def http_session(self, session):
        self._http_sessions.session = session

    def _context(self):
        return self._context_var.get() or self._fallback_context

    @property
    def log(self):
        context = self._context()
        if context.logger is None:
            context.logger = Logger()
        return context.logger

    @property
    def session(self):
        return self._context().session

    @session.setter
    def session(self, value):
        self._context().session = value

    @property
    def indexer(self):
        return self._context().date_parser

    @property
    def last_response_meta(self):
        return self._context().response_meta

    @last_response_meta.setter
    def last_response_meta(self, value):
        self._context().response_meta = dict(value or {})

    @property
    def _last_content_language(self):
        return self._context().content_language

    @_last_content_language.setter
    def _last_content_language(self, value):
        self._context().content_language = value

    def activate_context(self, context):
        """Return a context manager activating request-local state."""
        extractor = self

        class _Activation:
            def __enter__(self):
                self.token = extractor._context_var.set(context)
                return context

            def __exit__(self, exc_type, exc, tb):
                extractor._context_var.reset(self.token)
                return False

        return _Activation()

    def initfeed(self, document, base_url):
        """Inits feed to get data"""
        if document is None:
            feed_title = "News from " + base_url
            title_extracted = False
        else:
            t_nodes = document.xpath("//head/title")
            if len(t_nodes) > 0 and t_nodes[0].text is not None:
                feed_title = t_nodes[0].text.strip()
                title_extracted = True
            else:
                feed_title = "News from " + base_url
                title_extracted = False
        language = resolve_feed_language(
            override=self.default_language,
            document=document,
            content_language=self._last_content_language,
        )
        self.use_page_language(document)
        feed = {
            "title": feed_title,
            "language": language,
            "link": base_url,
            "description": feed_title,
            "items": [],
        }
        if self.session:
            self.session["debug"]["title_extracted"] = title_extracted
        self.log.save("initfeed", "Feed parsed")
        return feed

    def use_page_language(self, document=None, language=None):
        """Match dates with the page language's qddate parser first.

        The language is ``language``, else the explicit ``default_language``,
        else the page metadata (``<html lang>``, ``og:locale`` …), else the
        ``Content-Language`` header. Item text is not consulted: dates are read
        before the items exist. Without evidence, or for a language qddate does
        not know, only the general parser is used. The tag as written
        (``en-US``) also decides the order of ambiguous numeric dates; an
        explicit language without a region keeps the page's region when both
        name the same language.
        """
        context = self._context()
        headers = context.response_meta.get("headers") or {}
        header = headers.get("Content-Language") or headers.get("content-language")
        page = (
            detect_page_locale(document)
            or (str(header).split(",")[0].strip() if header else None)
            or self._last_content_language
        )
        tag = language or self.default_language or page
        locale = tag
        if (
            tag
            and page
            and normalize_language_tag(tag) == str(tag).strip().lower()
            and normalize_language_tag(page) == normalize_language_tag(tag)
        ):
            locale = page
        context.set_date_language(qddate_language(tag))
        context.date_locale = locale or None

    def narrowed_dates(self, patterns):
        """Context manager: match only ``patterns`` (qddate keys) inside the block."""
        return self._context().narrowed_dates(patterns)

    def ordered_dates(self, order):
        """Context manager: read ambiguous numeric dates as ``"dmy"`` or ``"mdy"``."""
        return self._context().ordered_dates(order)

    def _qddate_match(self, text):
        """``(match, matched_text, language)`` from the first parser that reads ``text``.

        The page language's parser is tried first. The general parser is the
        fallback for text with letters, so wrong page metadata does not lose
        dates; without letters only numeric patterns can match, and every
        parser has those.

        Results are remembered for the rest of the build: a page's date nodes
        are read for clusters, item blocks and annotations, and again by the
        spec built from them. A pattern restriction only removes candidates,
        so an unrestricted miss, or a match by one of the allowed patterns,
        is also the restricted result.
        """
        context = self._context()
        memo = context.date_memo()
        patterns = context.date_patterns
        key = (text, context.date_language, None if patterns is None else tuple(patterns))
        found = memo.get(key)
        if found is None and patterns is not None:
            free = memo.get((text, context.date_language, None))
            if free is not None and (free[0] is None or free[0]["pattern"]["key"] in patterns):
                found = free
        if found is None:
            found = self._match_parsers(text)
        memo[key] = found
        return found

    def _match_parsers(self, text):
        parsers = self._context().date_parsers()
        if not has_letters(text):
            parsers = parsers[:1]
        variants = None
        for language, parser in parsers:
            res = parser.match(text)
            if res:
                return res, text, language
            if variants is None:
                # "GENEVA, 29 July 2022", "Monday, January 31, 2022", "21-22 July 2022"
                variants = list(date_text_variants(text))
            for variant in variants:
                res = parser.match(variant)
                if res:
                    return res, variant, language
        return None, text, None

    def _reordered(self, res, date_text, order):
        """qddate's other reading of an ambiguous numeric date, in ``order``.

        ``05/06/2022`` reads as 5 June (``date_1``) and as 6 May
        (``date_usa``); ``match_all`` offers both. The other reading must keep
        the same fields (a time stays a time). Returns ``res`` when there is
        none, for instance a dotted date, which qddate only reads day first.
        """
        if numeric_order(res) in (None, order) or not is_ambiguous(res):
            return res
        context = self._context()
        memo = context.date_memo()
        patterns = context.date_patterns
        key = (
            "order",
            order,
            date_text,
            context.date_language,
            None if patterns is None else tuple(patterns),
        )
        if key not in memo:
            fields = set(res["values"].keys())
            memo[key] = next(
                (
                    alternative
                    for _language, parser in context.date_parsers()
                    for alternative in parser.match_all(date_text)
                    if numeric_order(alternative) == order
                    and set(alternative["values"].keys()) == fields
                ),
                res,
            )
        return memo[key]

    def read_text(self, text):
        """How ``text`` reads as a publication date: a :class:`DateReading` or ``None``."""
        if text is None:
            return None
        context = self._context()
        res, date_text, language = self._qddate_match(text)
        if self.session:
            self.session["debug"]["num_textcompared"] += 1
        if res:
            reordered = False
            if context.date_order:
                again = self._reordered(res, date_text, context.date_order)
                reordered, res = again is not res, again
            the_date = build_match_datetime(
                res, date_text, now=context.clock(), default_timezone=context.default_timezone
            )
            if the_date is None:
                self.log.save("match_text", "Rejected implausible or invalid date %r" % text)
                return None
            if self.session:
                self.session["debug"]["num_matched"] += 1
            return DateReading(
                key=res["pattern"]["key"],
                text=text,
                value=the_date,
                match=res,
                matched_text=date_text,
                parser_language=language,
                order=numeric_order(res),
                reordered=reordered,
                precision=match_precision(res),
            )
        relative = read_relative(
            text, now=context.clock(), default_timezone=context.default_timezone
        )
        if relative is not None:
            value, precision = relative
            if precision == DAY:
                value = anchor_day(value, context.default_timezone)
            if self.session:
                self.session["debug"]["num_matched"] += 1
            return DateReading(key="fuzzy", text=text, value=value, precision=precision)
        return None

    def match_text(self, text):
        """Matches text to the regular expressions.

        Always returns a 5-tuple ``(matched, key, pattern, text, date)`` so
        callers can unpack it uniformly whether or not a date was found.
        """
        reading = self.read_text(text)
        if reading is None:
            return False, None, None, None, None
        return reading.as_tuple()

    def read_date(self, node):
        """How an element reads as a publication date: ``<time datetime>``, else
        its text, else its tail. Returns a :class:`DateReading` or ``None``."""
        if node is None:
            return None
        if isinstance(getattr(node, "tag", None), str) and node.tag == "time":
            dt_attr = node.get("datetime")
            if dt_attr:
                parsed = read_datetime_attr(dt_attr, self._context().default_timezone)
                if parsed is not None:
                    display = (node.text or "").strip() or dt_attr
                    if self.session:
                        self.session["debug"]["num_datematched"] += 1
                        self.session["debug"]["num_matched"] += 1
                    return DateReading(
                        key="html:time", text=display, value=parsed[0], precision=parsed[1]
                    )
        for raw in (node.text, node.tail):
            if raw is None or not raw.strip():
                continue
            reading = self.read_text(str(raw.strip("/\\«[]»").strip().replace("\xa0", " ")))
            if reading is not None:
                if self.session:
                    self.session["debug"]["num_datematched"] += 1
                return reading
        return None

    def match_date(self, node):
        """Matches date to regular expressions. Uses  node as parameter"""
        reading = self.read_date(node)
        if reading is None:
            return None, None, None, None, None
        return reading.as_tuple()

    def _pick_title_from_anns(self, anns):
        """Prefers heading text over the first long text node in document order."""
        by_tag: dict[str, list] = {tag: [] for tag in _HEADING_TAGS}
        for ann in anns:
            if ann.node.tag is etree.Comment:
                continue
            tag = ann.tag if isinstance(ann.tag, str) else None
            if tag in by_tag:
                text = _element_text(ann.node).strip()
                if len(text) > 10:
                    by_tag[tag].append(text)
        for tag in _HEADING_TAGS:
            if by_tag[tag]:
                return by_tag[tag][0]
        for ann in anns:
            if ann.node.tag is etree.Comment:
                continue
            if TAG_TYPE_BOLD in ann.attrs and TAG_TYPE_DATE not in ann.attrs:
                text = _element_text(ann.node).strip()
                if len(text) > 10:
                    return text
        return None

    def getclusters(self, document, base_url):
        """
        Extracts all available text nodes with fixed text length
        :param document: original document, result of lxml parse
        :param base_url: base url of the processed webpage
        :return:
        """
        if document is None:
            self.session["debug"]["num_nodes"] = 0
            self.session["debug"]["num_clusters"] = 0
            self.session["debug"]["clusters"] = {}
            self.log.save("getclusters", "Document is None, returning empty clusters")
            return {}
        self.use_page_language(document)

        # Optimized XPath: exclude script/style nodes early for better performance
        nodes = document.xpath(
            "//*[not(self::script or self::style) and string-length(text())<%d]"
            % self.filtered_text_length
        )
        self.session["debug"]["num_nodes"] = len(nodes)
        self.log.save("getclusters", "Nodes extracted")

        # Early filtering: only check nodes that likely contain dates (have digits
        # or a relative-date keyword such as "yesterday"/"ago"). This avoids
        # expensive pattern matching on nodes that cannot be dates.
        potential_date_nodes = []
        for node in nodes:
            text = (node.text or "").strip()
            tail = (node.tail or "").strip()
            if any(
                value and (any(char.isdigit() for char in value) or looks_like_fuzzy_date(value))
                for value in (text, tail)
            ):
                potential_date_nodes.append(node)

        shared_node = None
        last = None
        last_d = {}
        last_path = None
        clusters = {}
        first = True
        # Only match patterns on potential date nodes
        for node in potential_date_nodes:
            reading = self.read_date(node)
            if reading is not None:
                path = TagPath(node)
                current = {"t_key": reading.key, "node": node, "reading": reading}
                if last is not None and last_path is not None and path.level == last_path.level:
                    snode = TagPath.getSharedNode(node, last)
                    if shared_node is None:
                        shared_node = snode
                    spath = document.getroottree().getpath(snode)
                    if spath not in clusters:
                        clusters[spath] = {"snode": snode, "nodes": []}
                    if first:
                        clusters[spath]["nodes"].append(last_d)
                        first = False
                    clusters[spath]["nodes"].append(current)

                last = node
                last_d = current
                last_path = path
        for info in clusters.values():
            self._order_cluster(info)
        self.session["debug"]["num_clusters"] = len(clusters)
        self.session["debug"]["clusters"] = clusters
        return clusters

    def _note_date_order(self, group, order):
        """Record a group's day/month order for diagnostics and ``explain``."""
        diagnostics = self._context().diagnostics
        if diagnostics is not None:
            entry = {"group": group, **order.to_dict()}
            orders = diagnostics.metadata.setdefault("date_order", [])
            if entry not in orders:
                orders.append(entry)

    def _order_cluster(self, info):
        """Choose one day/month order for a cluster and read its dates that way.

        ``info["date_order"]`` records the :class:`~newsworker.dates.DateOrder`;
        dates qddate read the other way get the chosen reading and pattern key.
        """
        order = choose_date_order(
            (node.get("reading") for node in info["nodes"]), self._context().date_locale
        )
        info["date_order"] = order
        if order.order is None:
            return
        with self.ordered_dates(order.order):
            for node in info["nodes"]:
                reading = node.get("reading")
                if reading is None or reading.order in (None, order.order):
                    continue
                again = self.read_date(node["node"])
                if again is not None:
                    node["reading"], node["t_key"] = again, again.key

    def process_clusters(self, base_url, clusters, feed):
        """Extracts news items from clustered date nodes into ``feed``.

        Orchestration only: for each cluster it resolves the shared container,
        builds the candidate item blocks (:meth:`_build_item_blocks`) and turns
        each block into a feed item (:meth:`_item_from_block`).
        """
        cache_block: dict[str, Any] = {"pats": []}
        self.log.save("process_clusters", "Start cluster processing")
        self.session["debug"]["tagblocks"] = []
        self.session["debug"]["annotations"] = []
        for path, node_info in list(clusters.items()):
            snode = node_info["snode"]
            nodes = node_info["nodes"]
            if snode.tag == "table":
                for ch in list(snode):
                    if ch.tag == "tbody":
                        snode = ch
                        break
            snode_path = TagPath(snode)
            # Position of each date node among its siblings under ``snode``.
            data = [list(TagPath(ni["node"], snode).values())[1] for ni in nodes]
            order = node_info.get("date_order")
            if order is not None and order.order is not None:
                self._note_date_order(path, order)
            with self.ordered_dates(order.order if order is not None else None):
                blocks = self._build_item_blocks(snode, snode_path, nodes, data)
                for block in blocks:
                    item = self._item_from_block(base_url, block, cache_block)
                    if item is not None:
                        feed["items"].append(item)
        feed["cache"] = cache_block
        self.log.save("process_clusters", "End cluster processing")
        return feed

    def _build_item_blocks(self, snode, snode_path, nodes, data):
        """Builds the list of :class:`TagBlock` item candidates for a cluster.

        Walks the date-node positions in reverse to size each item block by the
        gap to the next date, then aligns the final block's stride with the most
        common gap.
        """
        res = []
        avg_diff: dict[Any, Any] = {}
        last_block = None
        for i in range(len(data) - 1, -1, -1):
            if i != len(data) - 1:
                diff = data[i + 1] - data[i]
                avg_diff.setdefault(diff, 0)
                avg_diff[diff] += 1
                block = TagBlock(snode, snode_path, data[i], diff)
                (match, t_key, t_data, the_text, the_date) = self.match_date(nodes[i]["node"])
                use_tail = nodes[i]["node"].text is None
                text = nodes[i]["node"].text if not use_tail else nodes[i]["node"].tail
                if text is not None:
                    block.add_entity(
                        "pub_date",
                        TagPath(nodes[i]["node"]),
                        None,
                        text.strip(),
                        the_date,
                    )
                    res.append(block)
            else:
                diff = len(list(snode)) - data[i]
                if len(data) > 1:
                    block = TagBlock(snode, snode_path, data[i], diff)
                else:
                    block = TagBlock(snode, snode_path, data[i], None)
                last_block = block
                (match, t_key, t_data, the_text, the_date) = self.match_date(nodes[i]["node"])
                if nodes[i]["node"].text:
                    block.add_entity(
                        "pub_date",
                        TagPath(nodes[i]["node"]),
                        None,
                        the_text.strip(),
                        the_date,
                    )
                else:
                    use_tail = nodes[i]["node"].text is None
                    text = nodes[i]["node"].text if not use_tail else nodes[i]["node"].tail
                    if text is not None:
                        block.add_entity(
                            "pub_date",
                            TagPath(nodes[i]["node"]),
                            None,
                            text.strip(),
                            the_date,
                        )
        max_num = 0
        akey = 0
        for key, value in list(avg_diff.items()):
            if value > max_num:
                akey = key
                max_num = value
        if last_block is not None and akey and last_block.shift != akey:
            last_block.shift = akey
        res.reverse()
        if last_block is not None:
            res.append(last_block)
        return res

    def _item_from_block(self, base_url, block, cache_block):  # noqa: C901
        """Turns a single :class:`TagBlock` into a feed item dict, or ``None``.

        Classifies the block's annotations into title / description / links /
        images / date and assembles the item. Returns ``None`` when the block
        has no usable date or no entities.
        """
        anns = block.identify_entities()
        for ann in anns:
            (match, key, t_data, the_text, the_date) = self.match_date(ann.node)
            if match:
                ann.attrs.append(TAG_TYPE_DATE)
        title = self._pick_title_from_anns(anns)
        description = None
        description_parts = []  # Collect text parts for efficient joining
        url = None
        links = []
        link_nodes = []
        images = []
        the_date = None
        for ann in anns:
            if ann.node.tag is etree.Comment:
                continue
            if TAG_TYPE_TEXT in ann.attrs and TAG_TYPE_DATE not in ann.attrs:
                text_content = ann.node.text.strip() if ann.node.text else ""
                if len(text_content) > 10 and title is None:
                    title = text_content
                if (
                    description is None
                    and title is not None
                    and title != text_content
                    and len(text_content) > 10
                ):
                    description = text_content
                elif title is not None and description is not None and len(text_content) > 10:
                    description_parts.append(text_content)
            if TAG_TYPE_TAIL in ann.attrs:
                tail_content = ann.node.tail.strip() if ann.node.tail else ""
                if len(tail_content) > 10 and title is None:
                    title = tail_content
                if description is None and title is not None and len(tail_content) > 10:
                    description = tail_content
                elif title is not None and description is not None and len(tail_content) > 10:
                    description_parts.append(tail_content)
            if TAG_TYPE_HREF in ann.attrs and "href" in ann.node.attrib:
                clr = clean_url(get_abs_url(base_url, ann.node.attrib["href"]))
                if clr not in links:
                    links.append(clr)
                    link_nodes.append(ann.node)
            if TAG_TYPE_IMG in ann.attrs and "src" in ann.node.attrib:
                clr = clean_url(get_abs_url(base_url, ann.node.attrib["src"]))
                if clr not in images:
                    images.append(clr)
            if TAG_TYPE_DATE in ann.attrs:
                the_date = ann.node
        # Join collected description parts efficiently, once per item.
        if description_parts:
            if description is None:
                description = "\n".join(description_parts)
            else:
                description = description + "\n" + "\n".join(description_parts)
        if title is not None and description is None:
            description = title
        reading = self.read_date(the_date)
        if reading is None:
            return None
        t_key = reading.key
        if not block.entities:
            return None
        if t_key not in cache_block["pats"]:
            cache_block["pats"].append(t_key)
        md = hashlib.md5(usedforsecurity=False)
        md.update(block.entities["pub_date"][2].encode("utf8"))
        if title:
            md.update(title.encode("utf8"))
        if description:
            md.update(description.encode("utf8"))
        if url:
            md.update(url.encode("utf8"))
        ahash = md.hexdigest()
        item = {
            "title": title,
            "description": description,
            "pubdate": reading.value,
            "date_precision": reading.precision,
            "unique_id": str(ahash),
            "raw_html": block.as_html(),
        }
        item["extra"] = {"links": links, "images": images}
        if len(links) > 0:
            chosen = pick_link_node(link_nodes, title)
            index = link_nodes.index(chosen) if chosen is not None else 0
            item["link"] = clean_url(get_abs_url(base_url, links[index]))
        else:
            item["link"] = clean_url(base_url)
        return item

    def _load_cookies(self):
        """Returns a loaded cookie jar for ``cookies_file`` or ``None``.

        The jar is loaded once and cached. A missing or malformed file is
        ignored (no cookies) rather than aborting the fetch.
        """
        if not self.cookies_file:
            return None
        if self._cookie_jar is None:
            from http.cookiejar import MozillaCookieJar

            jar = MozillaCookieJar(self.cookies_file)
            try:
                jar.load(ignore_discard=True, ignore_expires=True)
            except (OSError, ValueError):
                self.log.save("fetch", "Could not load cookies from %s" % self.cookies_file)
            self._cookie_jar = jar
        return self._cookie_jar

    def fetch_result(
        self, url, user_agent=None, max_bytes=None, conditional=None, context=None
    ) -> FetchResult:
        """Fetch a URL through the shared policy and return response metadata."""
        active = context or self._context()
        validate_url(url)
        if self.respect_robots and not self._can_fetch_policy(url, user_agent):
            raise PermissionError("robots.txt disallows fetching %s" % url)
        headers = {}
        if conditional:
            if conditional.get("etag"):
                headers["If-None-Match"] = conditional["etag"]
            if conditional.get("last_modified"):
                headers["If-Modified-Since"] = conditional["last_modified"]
        policy = self._policy(user_agent, max_bytes)
        result = self.transport.fetch(FetchRequest(url=url, headers=headers), policy)
        active.response_meta = {
            **result.validators,
            "requested_url": result.requested_url,
            "effective_url": result.effective_url,
            "status": result.status,
            "headers": dict(result.headers),
        }
        if result.content_language:
            active.content_language = (
                result.content_language.split(",")[0].strip().split("-")[0].lower() or None
            )
        return result

    def _policy(self, user_agent=None, max_bytes=None):
        """The outbound policy for one request (cookies are loaded lazily)."""
        base = self.base_policy or FetchPolicy(
            timeout=self.timeout,
            max_bytes=self.max_bytes,
            verify_tls=self.verify_tls,
            legacy_tls_ciphers=getattr(self, "legacy_tls_ciphers", False),
            redirect_limit=getattr(self, "redirect_limit", 5),
            allowed_hosts=tuple(getattr(self, "allowed_hosts", ()) or ()),
            block_private_hosts=getattr(self, "block_private_hosts", True),
            allow_private_hosts=getattr(self, "allow_private_hosts", False),
            trusted_proxy=getattr(self, "trusted_proxy", False),
            proxy=self.proxy,
            extra_headers=self.extra_headers,
        )
        return replace(
            base,
            user_agent=user_agent or base.user_agent,
            max_bytes=max_bytes if max_bytes is not None else base.max_bytes,
            cookies=self._load_cookies(),
        )

    def _can_fetch_policy(self, url, user_agent):
        """Consult robots.txt (fetched through the same bounded transport and
        policy) and apply its ``Crawl-delay`` to the host's request pacing."""
        from urllib.parse import urlparse

        from .fetch import HOSTS
        from .tools import robots_rules

        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        policy = replace(self._policy(user_agent), max_bytes=min(self.max_bytes, 512 * 1024))
        rules = robots_rules(
            root, lambda robots_url: self.transport.fetch(FetchRequest(robots_url), policy).body
        )
        if rules is None:
            return True
        agent = user_agent or "*"
        try:
            delay = rules.crawl_delay(agent)
            if delay is None:
                rate = rules.request_rate(agent)
                delay = rate.seconds / rate.requests if rate and rate.requests else None
            if delay:
                HOSTS.note_crawl_delay((parsed.hostname or "").lower(), float(delay))
            return rules.can_fetch(agent, url)
        except Exception:
            return True

    def fetch(self, url, user_agent=None, max_bytes=None, conditional=None, context=None):
        """Fetches ``url`` and returns its bytes, capped at ``max_bytes``.

        Only ``http``/``https`` URLs are accepted (a baseline SSRF guard). TLS
        certificates are verified unless ``verify_tls`` was disabled. When
        ``respect_robots`` is set the site's ``robots.txt`` is consulted first and
        a disallowed URL raises :class:`PermissionError`. The response is streamed
        and aborted once it exceeds the size cap so a huge or hostile page cannot
        exhaust memory.

        When ``conditional`` is a mapping with ``etag``/``last_modified`` keys the
        request is made conditionally (``If-None-Match``/``If-Modified-Since``);
        a ``304 Not Modified`` response returns ``None`` so the caller can reuse
        its cached copy. Response validators are recorded on ``last_response_meta``.
        """
        try:
            result = self.fetch_result(
                url,
                user_agent=user_agent,
                max_bytes=max_bytes,
                conditional=conditional,
                context=context,
            )
            if result.not_modified:
                return None
            data = result.body
            if self.session:
                self.session["debug"]["page_length"] = len(data)
            return data
        except Exception as exc:
            from .fetch import FetchTimeout

            if isinstance(exc, FetchTimeout):
                self.log.save("fetch", f"Timeout while fetching {url}")
            else:
                self.log.save("fetch", f"Request error while fetching {url}: {exc}")
            raise

    def init_session(self):
        """Used to start internal debugging session"""
        self.session = {
            "debug": {"num_textcompared": 0, "num_matched": 0, "num_datematched": 0},
            "params": {},
        }
        self.session["debug"]["num_patterns"] = len(self.indexer.patterns)

    def clear_session(self):
        """Used to end internal debugging section"""
        session = copy(self.session)
        session["log"] = list(self.log.getlogs())
        self.log.clear()
        self.log.reset()
        self.session = None
        return session

    def _get_feed_active(self, url, data=None, user_agent=None, cached_p=None):
        """Return feed from url"""
        self.init_session()
        if cached_p is None:
            return self._build_feed(url, data, user_agent)
        with self.narrowed_dates(list(cached_p)):
            return self._build_feed(url, data, user_agent)

    def _build_feed(self, url, data, user_agent):
        if data is None:
            data = self.fetch(url, user_agent)
            self.log.save("get_rss", "Url fetched %s" % (url))
        edata = decode_html(data)
        self.log.save("get_rss", "Decode data")
        try:
            # Use memory-efficient parser that removes blank text nodes
            parser = etree.HTMLParser(remove_blank_text=True)
            document = fromstring(edata, parser=parser)
        except (ValueError, etree.ParserError, etree.XMLSyntaxError) as e:
            self.log.save("get_rss", f"Failed to parse HTML: {e}")
            document = None
        self.log.save("get_rss", "Parsed data")

        if document is None:
            self.log.save("get_rss", "Document is None, returning empty feed")
            feed = self.initfeed(None, url)
            session = self.clear_session()
            return feed, session

        feed = self.initfeed(document, url)
        clusters = self.getclusters(document, url)
        self.log.save("get_rss", "Clusters extracted")
        feed = self.process_clusters(url, clusters, feed)
        if not self.default_language:
            samples = [item.get("title") for item in feed.get("items", []) if item.get("title")]
            feed["language"] = resolve_feed_language(
                document=document,
                content_language=self._last_content_language,
                stored_language=feed.get("language"),
                text_samples=samples,
            )
        self.log.save("get_rss", "End of log")
        session = self.clear_session()
        return feed, session

    def get_feed(self, url, data=None, user_agent=None, cached_p=None, context=None):
        """Return a feed using isolated state for this logical build."""
        context = context or ExtractionContext(
            source="network" if data is None else "prefetched",
            base_url=url,
            default_timezone=self.default_timezone,
        )
        with self.activate_context(context):
            return self._get_feed_active(url, data=data, user_agent=user_agent, cached_p=cached_p)

    def learn_feed(self, url, user_agent=None, data=None):
        """Build a feed from a page without reusing cached date patterns.

        Retained for backwards compatibility; delegates to :meth:`get_feed`,
        which performs the same fetch/parse/cluster/extract pipeline.
        """
        return self.get_feed(url, data=data, user_agent=user_agent)
