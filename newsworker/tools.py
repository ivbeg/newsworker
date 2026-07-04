#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Supportive functions to help news extraction algorithms
"""
from bs4 import UnicodeDammit
import re
import threading
import time, datetime
from urllib.parse import urlparse, urljoin, parse_qs
from urllib.robotparser import RobotFileParser
from .consts import CLEANABLE_QUERY_KEYS


#: URL schemes considered safe to fetch server-side.
ALLOWED_URL_SCHEMES = ("http", "https")

#: Default User-Agent name used when consulting ``robots.txt``.
DEFAULT_ROBOTS_AGENT = "newsworker"

# Cache of parsed ``robots.txt`` rules keyed by scheme+host. A cached value of
# ``None`` means the file could not be retrieved and fetching is permitted
# (lenient policy). ``_ROBOTS_MISSING`` distinguishes "not attempted yet" from a
# cached ``None`` so we do not re-read on every call.
_ROBOTS_CACHE = {}
_ROBOTS_MISSING = object()
_ROBOTS_LOCK = threading.Lock()


def decode_html(html_string):
    return UnicodeDammit(html_string).unicode_markup


#: Seconds per relative-date unit (approximate for month/year).
_FUZZY_UNIT_SECONDS = {
    "second": 1,
    "sec": 1,
    "minute": 60,
    "min": 60,
    "hour": 3600,
    "hr": 3600,
    "day": 86400,
    "week": 604800,
    "month": 2592000,
    "year": 31536000,
}

_FUZZY_UNIT_ALT = "|".join(sorted(_FUZZY_UNIT_SECONDS, key=len, reverse=True))
_FUZZY_NUMERIC_RE = re.compile(
    r"\b(\d+)\s+(%s)s?\s+ago\b" % _FUZZY_UNIT_ALT, re.IGNORECASE
)
_FUZZY_ARTICLE_RE = re.compile(
    r"\b(?:a|an)\s+(%s)\s+ago\b" % _FUZZY_UNIT_ALT, re.IGNORECASE
)
_FUZZY_KEYWORDS = ("ago", "yesterday", "today", "just now", "moments ago", "a moment ago")


def looks_like_fuzzy_date(text):
    """Cheap check: does ``text`` plausibly contain a relative date phrase?"""
    if not text:
        return False
    low = text.lower()
    return any(kw in low for kw in _FUZZY_KEYWORDS)


def parse_fuzzy_date(text, now=None):
    """Resolves a relative date expression to a ``datetime``, or ``None``.

    Handles "just now"/"now", "today", "yesterday", "N <unit> ago" and
    "a/an <unit> ago" for seconds through years. ``now`` is injectable for tests.
    """
    if not text:
        return None
    now = now or datetime.datetime.now()
    s = text.strip().lower()
    if s in ("just now", "now", "moments ago", "a moment ago"):
        return now
    if s == "today":
        return now
    if s == "yesterday":
        return now - datetime.timedelta(days=1)
    m = _FUZZY_NUMERIC_RE.search(s)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        return now - datetime.timedelta(seconds=amount * _FUZZY_UNIT_SECONDS[unit])
    m = _FUZZY_ARTICLE_RE.search(s)
    if m:
        unit = m.group(1).lower()
        return now - datetime.timedelta(seconds=_FUZZY_UNIT_SECONDS[unit])
    return None


def find_next_link(document, base_url):
    """Returns the absolute URL of the "next page" link in ``document`` or ``None``.

    Looks for ``<link rel=next>`` / ``<a rel=next>`` first, then anchors whose
    class or text indicates pagination (e.g. "next", "older"). ``document`` is a
    parsed lxml element.
    """
    if document is None:
        return None
    try:
        rel_next = document.xpath(
            "//*[self::a or self::link]"
            "[contains(concat(' ', normalize-space(@rel), ' '), ' next ')]/@href"
        )
        if rel_next:
            return get_abs_url(base_url, rel_next[0])
        for anchor in document.xpath("//a[@href]"):
            classes = (anchor.get("class") or "").lower()
            text = (anchor.text_content() or "").strip().lower()
            if "next" in classes or "pagination-next" in classes:
                return get_abs_url(base_url, anchor.get("href"))
            if text in ("next", "next page", "older", "older posts", "»", "→"):
                return get_abs_url(base_url, anchor.get("href"))
    except Exception:
        return None
    return None


def detect_html_language(document):
    """Returns the primary language subtag from ``<html lang>``, or ``None``.

    ``document`` is a parsed lxml element. Region subtags are dropped so
    ``en-US`` becomes ``en``.
    """
    if document is None:
        return None
    try:
        langs = document.xpath("//html/@lang") or document.xpath("//@lang")
    except Exception:
        return None
    if not langs:
        return None
    value = (langs[0] or "").strip()
    if not value:
        return None
    return value.split("-")[0].lower()


def _robots_parser_for(root):
    """Returns a cached :class:`RobotFileParser` for ``root`` (or ``None``).

    ``None`` indicates the ``robots.txt`` could not be read; callers treat that
    leniently and allow the fetch.
    """
    with _ROBOTS_LOCK:
        cached = _ROBOTS_CACHE.get(root, _ROBOTS_MISSING)
    if cached is not _ROBOTS_MISSING:
        return cached
    parser = RobotFileParser()
    parser.set_url(urljoin(root, "/robots.txt"))
    try:
        parser.read()
    except Exception:
        # Network error, timeout, malformed file, etc. -> be lenient.
        parser = None
    with _ROBOTS_LOCK:
        _ROBOTS_CACHE[root] = parser
    return parser


def clear_robots_cache():
    """Clears the cached ``robots.txt`` rules (primarily for tests)."""
    with _ROBOTS_LOCK:
        _ROBOTS_CACHE.clear()


def can_fetch(url, user_agent=DEFAULT_ROBOTS_AGENT):
    """Returns whether ``robots.txt`` permits fetching ``url`` for ``user_agent``.

    The policy is intentionally lenient: when ``robots.txt`` is missing or cannot
    be retrieved/parsed the fetch is allowed. Parsed rules are cached per host so
    repeated fetches of the same site do not re-download the file.
    """
    parsed = urlparse(url or "")
    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES or not parsed.hostname:
        return True
    root = "%s://%s" % (parsed.scheme, parsed.netloc)
    parser = _robots_parser_for(root)
    if parser is None:
        return True
    try:
        return parser.can_fetch(user_agent or "*", url)
    except Exception:
        return True


def robots_crawl_delay(url, user_agent=DEFAULT_ROBOTS_AGENT):
    """Returns the ``Crawl-delay`` (seconds) for ``url`` or ``None`` when unset."""
    parsed = urlparse(url or "")
    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES or not parsed.hostname:
        return None
    root = "%s://%s" % (parsed.scheme, parsed.netloc)
    parser = _robots_parser_for(root)
    if parser is None:
        return None
    try:
        delay = parser.crawl_delay(user_agent or "*")
    except Exception:
        return None
    return float(delay) if delay is not None else None


def validate_url(url, allowed_hosts=None):
    """Validates a URL is safe to fetch server-side (a baseline SSRF guard).

    Only ``http`` / ``https`` URLs are permitted. When ``allowed_hosts`` is a
    non-empty iterable, the URL host must be a member of it. Returns ``True``
    on success and raises :class:`ValueError` otherwise.
    """
    parsed = urlparse(url or "")
    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
        raise ValueError(
            "Unsupported URL scheme %r (only http/https are allowed)" % parsed.scheme
        )
    if not parsed.hostname:
        raise ValueError("URL has no host: %r" % url)
    if allowed_hosts:
        host = parsed.hostname.lower()
        allowed = {h.lower() for h in allowed_hosts}
        if host not in allowed:
            raise ValueError("Host %r is not in the allowed hosts list" % host)
    return True


def get_abs_url(root_url, url):
    """Resolves ``url`` against ``root_url`` into an absolute URL.

    Uses :func:`urllib.parse.urljoin`, which correctly handles root-relative
    (``/x``), document-relative (``x``, ``./x``, ``../x``) and already-absolute
    URLs while preserving the base scheme (notably ``https``).
    """
    if not root_url:
        return url or ""
    # urljoin needs a scheme on the base to resolve host-relative links.
    if not urlparse(root_url).scheme:
        root_url = "http://" + root_url
    return urljoin(root_url, url or "")


def clean_url(url):
    """Removes just query parameters from url"""
    # clean url from jsession param
    THE_JS_KEY = ";jsessionid="
    n = url.find(THE_JS_KEY)
    if n > -1:
        thepath = url[:n] + url[n + len(THE_JS_KEY) + 32 :]
        url = thepath
    o = urlparse(url)

    # clean query
    if len(o.query) > 0:
        query = clean_urlquery(o.query)[0]
        if len(query) > 0:
            url = o.geturl().rsplit("?")[0] + "?" + query
        else:
            return o.geturl().rsplit("?")[0]
        return url
    #    print o
    return o.geturl()


def clean_urlquery(qs):
    """Removes _junk_ query parameters left by analytics systems"""
    items = parse_qs(qs, keep_blank_values=True)
    results = {}
    filtered = {}
    for k, v in list(items.items()):
        if k.lower() not in CLEANABLE_QUERY_KEYS:
            results[k] = v
        else:
            filtered[k] = v
    q = []
    for k, v in list(results.items()):
        q.append("%s=%s" % (k, v[0]))
    query = "&".join(q)
    return query, results, filtered


class Logger:
    def __init__(self, autostart=True):
        self.logs = []
        if autostart:
            self.reset()
        pass

    def reset(self):
        self.current = time.time()

    def clear(self):
        self.logs = []

    def save(self, code, msg, autoreset=True):
        current = time.time()
        record = {
            "dt": datetime.datetime.now().isoformat(),
            "time": current - self.current,
            "msg": msg,
            "code": code,
        }
        if autoreset:
            self.current = current
        self.logs.append(record)

    def getlogs(self):
        return self.logs
