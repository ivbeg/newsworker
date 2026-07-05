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
    return UnicodeDammit(html_string, is_html=True).unicode_markup


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


_DATETIME_ATTR_RE = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
    r"(?:T(?P<hour>\d{1,2}):(?P<minute>\d{1,2})(?::(?P<second>\d{1,2}))?)?"
)


def parse_datetime_attr(value):
    """Parses an HTML ``datetime`` attribute to a naive ``datetime``, or ``None``.

    Handles ISO-8601 date and date-time strings as emitted by WordPress and
    other CMSes (including timezone offsets, which are stripped).
    """
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except ValueError:
        pass
    m = _DATETIME_ATTR_RE.match(value)
    if not m:
        return None
    parts = {key: int(m.group(key)) for key in ("year", "month", "day") if m.group(key)}
    if m.group("hour") is not None:
        parts["hour"] = int(m.group("hour"))
        parts["minute"] = int(m.group("minute"))
        if m.group("second") is not None:
            parts["second"] = int(m.group("second"))
    try:
        return datetime.datetime(**parts)
    except ValueError:
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


def normalize_language_tag(value):
    """Returns the primary language subtag from a BCP 47 tag, or ``None``."""
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    primary = re.split(r"[-_]", value, maxsplit=1)[0].lower()
    return primary or None


def detect_html_language(document):
    """Returns the primary language subtag from ``<html lang>``, or ``None``.

    ``document`` is a parsed lxml element. Region subtags are dropped so
    ``en-US`` becomes ``en``.
    """
    if document is None:
        return None
    try:
        langs = document.xpath("//html/@lang")
    except Exception:
        return None
    if not langs:
        return None
    return normalize_language_tag(langs[0])


def detect_page_language_metadata(document):
    """Returns a language subtag from common HTML metadata, or ``None``.

    Checks ``<html lang>``, ``<meta http-equiv="content-language">``,
    ``og:locale``, and ``<meta name="language">`` in that order.
    """
    if document is None:
        return None
    queries = (
        "//html/@lang",
        (
            "//meta[translate(@http-equiv, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz')='content-language']/@content"
        ),
        "//meta[@property='og:locale']/@content",
        "//meta[@name='og:locale']/@content",
        "//meta[@name='language']/@content",
    )
    for query in queries:
        try:
            values = document.xpath(query)
        except Exception:
            continue
        for value in values:
            lang = normalize_language_tag(value)
            if lang:
                return lang
    return None


#: Distinctive letters used to guess Latin-script languages from item text.
_LATIN_LANGUAGE_HINTS = {
    "de": "äöüßÄÖÜ",
    "fr": "àâæçéèêëïîôùûüÿœÀÂÆÇÉÈÊËÏÎÔÙÛÜŸŒ",
    "es": "áéíóúñü¿¡ÁÉÍÓÚÑ",
    "pt": "ãõáâàçéêíóôúÃÕÁÂÀÇÉÊÍÓÔÚ",
    "it": "àèéìíîòóùúÀÈÉÌÍÎÒÓÙÚ",
}

#: Ukrainian-specific Cyrillic letters (vs Russian/Belarusian defaults).
_UKRAINIAN_CHARS = set("іїєґІЇЄҐ")


def _script_counts(text):
    """Returns rough script counts for ``text``."""
    counts = {
        "cyrillic": 0,
        "greek": 0,
        "arabic": 0,
        "hebrew": 0,
        "hiragana_katakana": 0,
        "hangul": 0,
        "cjk": 0,
        "thai": 0,
        "devanagari": 0,
        "latin": 0,
    }
    for ch in text:
        if not ch.isalpha():
            continue
        code = ord(ch)
        if 0x0400 <= code <= 0x04FF:
            counts["cyrillic"] += 1
        elif 0x0370 <= code <= 0x03FF:
            counts["greek"] += 1
        elif 0x0600 <= code <= 0x06FF:
            counts["arabic"] += 1
        elif 0x0590 <= code <= 0x05FF:
            counts["hebrew"] += 1
        elif 0x3040 <= code <= 0x30FF:
            counts["hiragana_katakana"] += 1
        elif 0xAC00 <= code <= 0xD7AF:
            counts["hangul"] += 1
        elif 0x4E00 <= code <= 0x9FFF:
            counts["cjk"] += 1
        elif 0x0E00 <= code <= 0x0E7F:
            counts["thai"] += 1
        elif 0x0900 <= code <= 0x097F:
            counts["devanagari"] += 1
        else:
            counts["latin"] += 1
    return counts


def _detect_latin_language(text):
    """Guesses a Latin-script language from distinctive letters in ``text``."""
    scores = {lang: 0 for lang in _LATIN_LANGUAGE_HINTS}
    for lang, chars in _LATIN_LANGUAGE_HINTS.items():
        scores[lang] = sum(text.count(ch) for ch in chars)
    best_lang, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score < 2:
        return None
    return best_lang


def detect_text_language(text):
    """Guesses a language subtag from visible text, or ``None`` when unsure."""
    if not text:
        return None
    text = text.strip()
    if not text:
        return None
    counts = _script_counts(text)
    letters = sum(counts.values())
    if letters < 8:
        return None

    dominant = max(counts, key=counts.get)
    dominant_count = counts[dominant]
    if dominant_count < max(8, int(letters * 0.25)):
        return _detect_latin_language(text)

    if dominant == "cyrillic":
        if any(ch in _UKRAINIAN_CHARS for ch in text):
            return "uk"
        return "ru"
    if dominant == "greek":
        return "el"
    if dominant == "arabic":
        return "ar"
    if dominant == "hebrew":
        return "he"
    if dominant == "thai":
        return "th"
    if dominant == "devanagari":
        return "hi"
    if dominant == "hangul":
        return "ko"
    if dominant == "hiragana_katakana":
        return "ja"
    if dominant == "cjk":
        if counts["hiragana_katakana"] or counts["hangul"]:
            return "ja" if counts["hiragana_katakana"] >= counts["hangul"] else "ko"
        return "zh"
    return _detect_latin_language(text)


def detect_text_language_from_samples(samples):
    """Votes across multiple text samples and returns the winning language."""
    votes = {}
    for sample in samples or []:
        lang = detect_text_language(sample)
        if lang:
            votes[lang] = votes.get(lang, 0) + 1
    if not votes:
        return None
    return max(votes, key=votes.get)


def resolve_feed_language(
    override=None,
    document=None,
    content_language=None,
    stored_language=None,
    text_samples=None,
):
    """Resolves the feed language from overrides, metadata, headers, and text.

    When metadata only declares English (or is absent) but extracted item text
    clearly indicates another language, the text-based guess wins.
    """
    override_lang = normalize_language_tag(override)
    if override_lang:
        return override_lang

    meta_lang = detect_page_language_metadata(document)
    header_lang = normalize_language_tag(content_language)
    stored_lang = normalize_language_tag(stored_language)
    text_lang = detect_text_language_from_samples(text_samples)

    if text_lang and text_lang != "en":
        weak_metadata = meta_lang in (None, "en") and header_lang in (None, "en")
        weak_stored = stored_lang in (None, "en")
        if weak_metadata and weak_stored:
            return text_lang

    for lang in (meta_lang, header_lang, stored_lang, text_lang):
        if lang:
            return lang
    return "en"


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
