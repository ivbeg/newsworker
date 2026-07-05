#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
"""


import hashlib
import requests.exceptions
from copy import copy
import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# Suppress InsecureRequestWarning for unverified HTTPS requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from lxml.html import fromstring
from lxml import etree
from qddate import DateParser
from .tools import (
    get_abs_url,
    decode_html,
    clean_url,
    validate_url,
    can_fetch,
    parse_fuzzy_date,
    looks_like_fuzzy_date,
    parse_datetime_attr,
    resolve_feed_language,
    Logger,
)
from .tagmapper import TagPath, TagBlock
from .consts import (
    TAG_TYPE_DATE,
    TAG_TYPE_TAIL,
    TAG_TYPE_TEXT,
    TAG_TYPE_HREF,
    TAG_TYPE_IMG,
    TAG_TYPE_BOLD,
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
        self.log = Logger()
        self.debug = debug
        self.log.save("initclass", "Start loading patterns")
        self.indexer = DateParser(generate=True)
        self.log.save("initclass", "End loading patterns")
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
        #: Language captured from the last response's Content-Language header.
        self._last_content_language = None
        #: Validators (``etag``/``last_modified``) from the last response.
        self.last_response_meta = {}

        # Create session with connection pooling
        self.http_session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )
        self.http_session.mount("http://", adapter)
        self.http_session.mount("https://", adapter)

        self.session = None

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

    def match_text(self, text):
        """Matches text to the regular expressions.

        Always returns a 5-tuple ``(matched, key, pattern, text, date)`` so
        callers can unpack it uniformly whether or not a date was found.
        """
        if text is None:
            return False, None, None, None, None
        res = self.indexer.match(text)
        #        print('Compare %s ' % (text))
        if self.session:
            self.session["debug"]["num_textcompared"] += 1
        #        self.log.save('match_text', 'Text %s against patterns, result %s' % (text, str(p)))
        if res:
            r = res["values"]
            p = res["pattern"]
            d = {"month": 0, "day": 0, "year": 0}
            if "noyear" in p and p["noyear"] == True:
                d["year"] = datetime.datetime.now().year
            for k, v in list(r.items()):
                d[k] = int(v)
            try:
                the_date = datetime.datetime(**d)
                if self.session:
                    self.session["debug"]["num_matched"] += 1
                return True, p["key"], p, text, the_date
            except (ValueError, TypeError, KeyError) as e:
                self.log.save("match_text", f"Failed to create datetime: {e}")
                return False, None, None, None, None
        fuzzy_date = parse_fuzzy_date(text)
        if fuzzy_date is not None:
            if self.session:
                self.session["debug"]["num_matched"] += 1
            return True, "fuzzy", {"key": "fuzzy"}, text, fuzzy_date
        return False, None, None, None, None

    def match_date(self, node):
        """Matches date to regular expressions. Uses  node as parameter"""
        if node is None:
            return None, None, None, None, None
        if isinstance(getattr(node, "tag", None), str) and node.tag == "time":
            dt_attr = node.get("datetime")
            if dt_attr:
                the_date = parse_datetime_attr(dt_attr)
                if the_date is not None:
                    display = (node.text or "").strip() or dt_attr
                    if self.session:
                        self.session["debug"]["num_datematched"] += 1
                        self.session["debug"]["num_matched"] += 1
                    return True, "html:time", {"key": "html:time"}, display, the_date
        text_1 = None
        text_2 = None

        if node.text is not None and len(node.text.strip()) > 0:
            text_1 = str(node.text.strip("/\\«[]»").strip().replace("\xA0", " "))
        if node.tail is not None and len(node.tail.strip()) > 0:
            text_2 = str(node.tail.strip("/\\«[]»").strip().replace("\xA0", " "))
        if text_1 is None and text_2 is None:
            return None, None, None, None, None
        #        self.log.save('match_date', 'Matching date text: ' + unicode(text_1))
        #        self.log.save('match_date', 'Matching date tail: ' + unicode(text_2))
        if text_1 is not None:
            results = self.match_text(text_1)
            if results[0] is True:
                if self.session:
                    self.session["debug"]["num_datematched"] += 1
                return results
        if text_2 is not None:
            results = self.match_text(text_2)
            if results[0] is True:
                if self.session:
                    self.session["debug"]["num_datematched"] += 1
                return results
        return None, None, None, None, None

    def _pick_title_from_anns(self, anns):
        """Prefers heading text over the first long text node in document order."""
        by_tag = {tag: [] for tag in _HEADING_TAGS}
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
        
        # Optimized XPath: exclude script/style nodes early for better performance
        nodes = document.xpath(
            "//*[not(self::script or self::style) and string-length(text())<%d]" % self.filtered_text_length
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
            if text and (
                any(char.isdigit() for char in text) or looks_like_fuzzy_date(text)
            ):
                potential_date_nodes.append(node)
            elif tail and (
                any(char.isdigit() for char in tail) or looks_like_fuzzy_date(tail)
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
            (match, t_key, t_data, the_text, the_date) = self.match_date(node)
            if match:
                path = TagPath(node)
                if last is not None:
                    if path.level == last_path.level:
                        snode = TagPath.getSharedNode(node, last)
                        if shared_node is None:
                            shared_node = snode
                        spath = document.getroottree().getpath(snode)
                        if spath not in clusters:
                            clusters[spath] = {"snode": snode, "nodes": []}
                        if first:
                            clusters[spath]["nodes"].append(last_d)
                            first = False
                        clusters[spath]["nodes"].append({"t_key": t_key, "node": node})

                last = node
                last_d = {"t_key": t_key, "node": node}
                last_path = path
        self.session["debug"]["num_clusters"] = len(clusters)
        self.session["debug"]["clusters"] = clusters
        return clusters

    def process_clusters(self, base_url, clusters, feed):
        """Extracts news items from clustered date nodes into ``feed``.

        Orchestration only: for each cluster it resolves the shared container,
        builds the candidate item blocks (:meth:`_build_item_blocks`) and turns
        each block into a feed item (:meth:`_item_from_block`).
        """
        cache_block = {"pats": []}
        self.log.save("process_clusters", "Start cluster processing")
        self.session["debug"]["tagblocks"] = []
        self.session["debug"]["annotations"] = []
        for _p, node_info in list(clusters.items()):
            snode = node_info["snode"]
            nodes = node_info["nodes"]
            if snode.tag == "table":
                for ch in snode.getchildren():
                    if ch.tag == "tbody":
                        snode = ch
                        break
            snode_path = TagPath(snode)
            # Position of each date node among its siblings under ``snode``.
            data = [list(TagPath(ni["node"], snode).values())[1] for ni in nodes]
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
        avg_diff = {}
        last_block = None
        for i in range(len(data) - 1, -1, -1):
            if i != len(data) - 1:
                diff = data[i + 1] - data[i]
                avg_diff.setdefault(diff, 0)
                avg_diff[diff] += 1
                block = TagBlock(snode, snode_path, data[i], diff)
                (match, t_key, t_data, the_text, the_date) = self.match_date(
                    nodes[i]["node"]
                )
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
                diff = len(snode.getchildren()) - data[i]
                if len(data) > 1:
                    block = TagBlock(snode, snode_path, data[i], diff)
                else:
                    block = TagBlock(snode, snode_path, data[i], None)
                last_block = block
                (match, t_key, t_data, the_text, the_date) = self.match_date(
                    nodes[i]["node"]
                )
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
                    text = (
                        nodes[i]["node"].text
                        if not use_tail
                        else nodes[i]["node"].tail
                    )
                    if text is not None:
                        block.add_entity(
                            "pub_date",
                            TagPath(nodes[i]["node"]),
                            None,
                            text.strip(),
                            the_date,
                        )
        # NOTE: this picks the last non-zero gap rather than the true mode
        # (``max_num`` is never updated); preserved as-is to keep the extraction
        # output stable. See the maintainer notes for a possible follow-up.
        max_num = 0
        akey = 0
        for key, value in list(avg_diff.items()):
            if value > max_num:
                akey = key
        if last_block.shift != akey:
            last_block.shift = akey
        res.reverse()
        res.append(last_block)
        return res

    def _item_from_block(self, base_url, block, cache_block):
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
                elif (
                    title is not None
                    and description is not None
                    and len(text_content) > 10
                ):
                    description_parts.append(text_content)
            if TAG_TYPE_TAIL in ann.attrs:
                tail_content = ann.node.tail.strip() if ann.node.tail else ""
                if len(tail_content) > 10 and title is None:
                    title = tail_content
                if (
                    description is None
                    and title is not None
                    and len(tail_content) > 10
                ):
                    description = tail_content
                elif (
                    title is not None
                    and description is not None
                    and len(tail_content) > 10
                ):
                    description_parts.append(tail_content)
            if TAG_TYPE_HREF in ann.attrs and "href" in ann.node.attrib:
                clr = clean_url(get_abs_url(base_url, ann.node.attrib["href"]))
                if clr not in links:
                    links.append(clr)
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
        (match, t_key, t_data, the_text, a_date) = self.match_date(the_date)
        if match is None:
            return None
        if not block.entities:
            return None
        if t_key not in cache_block["pats"]:
            cache_block["pats"].append(t_key)
        md = hashlib.md5()
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
            "pubdate": a_date,
            "unique_id": str(ahash),
            "raw_html": block.as_html(),
        }
        item["extra"] = {"links": links, "images": images}
        if len(links) > 0:
            item["link"] = clean_url(get_abs_url(base_url, links[0]))
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

    def fetch(self, url, user_agent=None, max_bytes=None, conditional=None):
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
        validate_url(url)
        if self.respect_robots and not can_fetch(url, user_agent):
            raise PermissionError("robots.txt disallows fetching %s" % url)
        limit = max_bytes if max_bytes is not None else self.max_bytes
        headers = dict(self.extra_headers)
        if user_agent is not None:
            headers["User-agent"] = user_agent
        if conditional:
            if conditional.get("etag"):
                headers["If-None-Match"] = conditional["etag"]
            if conditional.get("last_modified"):
                headers["If-Modified-Since"] = conditional["last_modified"]
        proxies = None
        if self.proxy:
            proxies = {"http": self.proxy, "https": self.proxy}
        try:
            with self.http_session.get(
                url,
                headers=headers,
                verify=self.verify_tls,
                timeout=self.timeout,
                proxies=proxies,
                cookies=self._load_cookies(),
                stream=True,
            ) as u:
                if getattr(u, "status_code", None) == 304:
                    return None
                u.raise_for_status()  # Raise an exception for bad status codes
                self.last_response_meta = {
                    "etag": u.headers.get("ETag"),
                    "last_modified": u.headers.get("Last-Modified"),
                }
                content_language = u.headers.get("Content-Language")
                if content_language:
                    self._last_content_language = (
                        content_language.split(",")[0].strip().split("-")[0].lower()
                        or None
                    )
                declared = u.headers.get("Content-Length")
                if declared and declared.isdigit() and int(declared) > limit:
                    raise ValueError(
                        "Response too large: %s bytes declared (max %d)"
                        % (declared, limit)
                    )
                chunks = []
                total = 0
                for chunk in u.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > limit:
                        raise ValueError(
                            "Response exceeded max size of %d bytes" % limit
                        )
                    chunks.append(chunk)
                data = b"".join(chunks)
            if self.session:
                self.session["debug"]["page_length"] = len(data)
            return data
        except requests.exceptions.Timeout:
            self.log.save("fetch", f"Timeout while fetching {url}")
            raise
        except requests.exceptions.RequestException as e:
            self.log.save("fetch", f"Request error while fetching {url}: {e}")
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
        session["log"] = self.log.getlogs()
        self.log.reset()
        self.session = None
        return session

    def get_feed(self, url, data=None, user_agent=None, cached_p=None):
        """Return feed from url"""
        self.init_session()
        if cached_p is not None:
            self.indexer.startSession(cached_p)
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
            samples = [
                item.get("title")
                for item in feed.get("items", [])
                if item.get("title")
            ]
            feed["language"] = resolve_feed_language(
                document=document,
                content_language=self._last_content_language,
                stored_language=feed.get("language"),
                text_samples=samples,
            )
        if cached_p is not None:
            self.indexer.endSession()
        self.log.save("get_rss", "End of log")
        session = self.clear_session()
        return feed, session

    def learn_feed(self, url, user_agent=None, data=None):
        """Build a feed from a page without reusing cached date patterns.

        Retained for backwards compatibility; delegates to :meth:`get_feed`,
        which performs the same fetch/parse/cluster/extract pipeline.
        """
        return self.get_feed(url, data=data, user_agent=user_agent)
