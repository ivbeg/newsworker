#!/usr/bin/env python
"""
Supportive functions to help news extraction algorithms
"""

import datetime
import hashlib
import re
import threading
import time
from collections import Counter, OrderedDict
from urllib.parse import unquote_plus, urljoin, urlparse, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

from bs4 import UnicodeDammit

from .consts import CLEANABLE_QUERY_KEYS

#: URL schemes considered safe to fetch server-side.
ALLOWED_URL_SCHEMES = ("http", "https")

#: Default User-Agent name used when consulting ``robots.txt``.
DEFAULT_ROBOTS_AGENT = "newsworker"

#: Largest ``robots.txt`` read; a bigger file counts as unreadable (allowed).
ROBOTS_MAX_BYTES = 512 * 1024

_ROBOTS_MISSING = object()


class _RobotsCache:
    """Parsed ``robots.txt`` rules per scheme+host, bounded in size and age.

    A cached ``None`` means the file could not be retrieved and fetching is
    permitted (lenient policy). Entries expire after a day (RFC 9309 advises
    against longer caching) and the oldest are dropped beyond ``max_entries``,
    so a long-running server does not grow without bound.
    """

    def __init__(self, ttl=86400.0, max_entries=4096, clock=time.monotonic):
        self.ttl = ttl
        self.max_entries = max_entries
        self._clock = clock
        self._entries = OrderedDict()
        self._lock = threading.Lock()

    def get(self, root, default=None):
        with self._lock:
            entry = self._entries.get(root)
            if entry is None:
                return default
            parser, stored = entry
            if self._clock() - stored > self.ttl:
                del self._entries[root]
                return default
            return parser

    def __setitem__(self, root, parser):
        with self._lock:
            self._entries[root] = (parser, self._clock())
            self._entries.move_to_end(root)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def clear(self):
        with self._lock:
            self._entries.clear()

    def __len__(self):
        return len(self._entries)


_ROBOTS_CACHE = _RobotsCache()


def decode_html(html_string):
    return UnicodeDammit(html_string, is_html=True).unicode_markup


def looks_like_fuzzy_date(text):
    """Cheap check for a relative date keyword ("ago", "вчера", "hace", ...)."""
    from .relative import looks_relative

    return looks_relative(text)


def normalize_datetime(value, default_timezone="UTC"):
    """Return a publication time as an aware UTC datetime.

    Naive values are interpreted in ``default_timezone``.  This helper is the
    canonical extraction/output boundary for publication instants.
    """
    if value is None:
        return None
    if not isinstance(value, datetime.datetime):
        raise TypeError("publication time must be a datetime")
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(default_timezone))
    return value.astimezone(datetime.timezone.utc)


def parse_fuzzy_date(text, now=None, default_timezone="UTC"):
    """Resolves a relative date expression to a ``datetime``, or ``None``.

    Understands "just now", "today", "yesterday [at 14:30]" and "N <unit> ago"
    in English, Russian, Ukrainian, German, French, Spanish, Italian and
    Portuguese. ``now`` is injectable for tests.
    """
    from .relative import parse_relative

    return parse_relative(text, now=now, default_timezone=default_timezone)


_DATETIME_ATTR_RE = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
    r"(?:T(?P<hour>\d{1,2}):(?P<minute>\d{1,2})(?::(?P<second>\d{1,2}))?)?"
)


def parse_datetime_attr(value, default_timezone="UTC"):
    """Parses an HTML ``datetime`` attribute to an aware UTC datetime, or ``None``.

    Handles ISO-8601 date and date-time strings as emitted by WordPress and
    other CMSes. Explicit offsets are preserved as instants and naive values use
    ``default_timezone``.
    """
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return normalize_datetime(dt, default_timezone)
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
        return normalize_datetime(datetime.datetime(**parts), default_timezone)  # type: ignore[arg-type]
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


_LANGUAGE_METADATA_QUERIES = (
    "//html/@lang",
    (
        "//meta[translate(@http-equiv, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        "'abcdefghijklmnopqrstuvwxyz')='content-language']/@content"
    ),
    "//meta[@property='og:locale']/@content",
    "//meta[@name='og:locale']/@content",
    "//meta[@name='language']/@content",
)


def detect_page_locale(document):
    """Returns the first language tag from common HTML metadata as written
    (``en-US``, ``en_GB``), or ``None``.

    Checks ``<html lang>``, ``<meta http-equiv="content-language">``,
    ``og:locale``, and ``<meta name="language">`` in that order.
    """
    if document is None:
        return None
    for query in _LANGUAGE_METADATA_QUERIES:
        try:
            values = document.xpath(query)
        except Exception:  # noqa: S112 - a query the document cannot answer is skipped
            continue
        for value in values:
            if normalize_language_tag(value):
                return str(value).strip().split(",")[0].strip()
    return None


def detect_page_language_metadata(document):
    """Returns a language subtag from common HTML metadata, or ``None``.

    Checks ``<html lang>``, ``<meta http-equiv="content-language">``,
    ``og:locale``, and ``<meta name="language">`` in that order.
    """
    return normalize_language_tag(detect_page_locale(document))


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


def detect_text_language(text):  # noqa: C901
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
    votes: dict[str, int] = {}
    for sample in samples or []:
        lang = detect_text_language(sample)
        if lang:
            votes[lang] = votes.get(lang, 0) + 1
    if not votes:
        return None
    return max(votes, key=lambda lang: votes[lang])


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


def resolve_feed_language_with_diagnostics(**kwargs):
    """Resolve language and return stable override/fallback reason codes."""
    override = normalize_language_tag(kwargs.get("override"))
    language = resolve_feed_language(**kwargs)
    if override:
        return language, {"reason": "explicit_override", "ambiguous": False}
    document = kwargs.get("document")
    metadata = detect_page_language_metadata(document)
    header = normalize_language_tag(kwargs.get("content_language"))
    text = detect_text_language_from_samples(kwargs.get("text_samples"))
    candidates = {candidate for candidate in (metadata, header, text) if candidate}
    if not candidates:
        return language, {"reason": "default_fallback", "ambiguous": True}
    if len(candidates) > 1:
        return language, {
            "reason": "ambiguous_evidence",
            "ambiguous": True,
            "candidates": sorted(candidates),
        }
    return language, {"reason": "automatic_evidence", "ambiguous": False}


def robots_rules(root, fetch):
    """Return cached ``robots.txt`` rules for ``root`` (``scheme://host[:port]``).

    ``fetch(url)`` returns the body bytes; any error (404, timeout, policy
    rejection) caches ``None``, which callers treat as "allowed".
    """
    cached = _ROBOTS_CACHE.get(root, _ROBOTS_MISSING)
    if cached is not _ROBOTS_MISSING:
        return cached
    robots_url = urljoin(root, "/robots.txt")
    parser: RobotFileParser | None = None
    try:
        body = fetch(robots_url)
        rules = RobotFileParser()
        rules.set_url(robots_url)
        rules.parse(body.decode("utf-8", "replace").splitlines())
        parser = rules
    except Exception:
        parser = None
    _ROBOTS_CACHE[root] = parser
    return parser


def robots_allows(url, fetch, agent="*"):
    """Return whether ``robots.txt`` lets ``agent`` fetch ``url``.

    ``fetch(robots_url)`` returns the body bytes through the caller's own
    transport and policy, capped at :data:`ROBOTS_MAX_BYTES`. A missing or
    unreadable ``robots.txt`` allows the fetch (lenient policy). The
    ``Crawl-delay`` (or ``Request-rate``) for ``agent`` is applied to the
    host's request pacing on :data:`newsworker.fetch.HOSTS`.
    """
    from .fetch import HOSTS

    parsed = urlparse(url or "")
    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES or not parsed.hostname:
        return True
    rules = robots_rules(f"{parsed.scheme}://{parsed.netloc}", fetch)
    if rules is None:
        return True
    agent = agent or "*"
    try:
        delay = rules.crawl_delay(agent)
        if delay is None:
            rate = rules.request_rate(agent)
            delay = rate.seconds / rate.requests if rate and rate.requests else None
        if delay:
            HOSTS.note_crawl_delay(parsed.hostname.lower(), float(delay))
        return rules.can_fetch(agent, url)
    except Exception:
        return True


def _default_robots_fetch(url):
    from .fetch import FetchPolicy, FetchRequest, RequestsTransport

    policy = FetchPolicy(timeout=10, max_bytes=ROBOTS_MAX_BYTES, user_agent=DEFAULT_ROBOTS_AGENT)
    return RequestsTransport().fetch(FetchRequest(url), policy).body


def _robots_parser_for(root):
    """Rules for ``root`` fetched with the default (private-address-blocking) policy."""
    return robots_rules(root, _default_robots_fetch)


def clear_robots_cache():
    """Clears the cached ``robots.txt`` rules (primarily for tests)."""
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
        raise ValueError("Unsupported URL scheme %r (only http/https are allowed)" % parsed.scheme)
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


#: URL schemes that may appear as item links or images in produced feeds.
SAFE_LINK_SCHEMES = ("http", "https")


def is_safe_link(url):
    """Return whether ``url`` is an absolute http(s) link safe to publish."""
    if not url or not isinstance(url, str):
        return False
    return urlparse(url.strip()).scheme.lower() in SAFE_LINK_SCHEMES


def sanitize_feed_links(feed, fallback_url=None):
    """Drop ``javascript:``, ``data:`` and other non-http(s) links from ``feed``.

    Pages are untrusted input; a crafted ``<a href="javascript:...">`` must not
    reach feed readers or the HTML preview.  An unsafe item link falls back to
    the page URL, the same as an item without a link.
    """
    for item in feed.get("items", []) or []:
        link = item.get("link")
        if link and not is_safe_link(link):
            item["link"] = fallback_url if is_safe_link(fallback_url) else None
        extra = item.get("extra")
        if isinstance(extra, dict):
            for key in ("links", "images"):
                values = extra.get(key)
                if isinstance(values, list):
                    extra[key] = [value for value in values if is_safe_link(value)]
        image = item.get("image")
        if image and not is_safe_link(image):
            item.pop("image", None)
    return feed


_HEADING_TAG_NAMES = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


def _node_text(node):
    return " ".join("".join(node.itertext()).split())


def pick_link_node(candidates, title=None):
    """Choose the article link among an item's ``<a href>`` nodes.

    The first link in an item is often a category, tag or author link
    (issue #19). Prefer, in order: the link whose text is the title, a link
    inside a heading, then the link with the longest text; fall back to the
    first candidate.
    """
    links = [node for node in candidates if node.get("href")]
    if not links:
        return None
    wanted = " ".join((title or "").split()).casefold()
    if wanted:
        for node in links:
            text = _node_text(node).casefold()
            if text and (text == wanted or (len(text) > 10 and (text in wanted or wanted in text))):
                return node
    for node in links:
        if any(
            isinstance(ancestor.tag, str) and ancestor.tag.lower() in _HEADING_TAG_NAMES
            for ancestor in node.iterancestors()
        ) or any(
            isinstance(child.tag, str) and child.tag.lower() in _HEADING_TAG_NAMES
            for child in node.iterdescendants()
        ):
            return node
    longest = max(links, key=lambda node: len(_node_text(node)))
    return longest if len(_node_text(longest)) > 10 else links[0]


def assign_item_identities(items, page_url=None):
    """Give items a ``unique_id`` derived from their own link.

    Strategies hash the date text, title, description and link; that hash
    changes whenever a site edits a teaser, so ``watch`` and feed readers would
    treat the edited item as new.  The hash is kept as ``content_hash`` (and
    still serves as the id for items without a link of their own or whose link
    is shared with other items on the page).
    """
    page = clean_url(page_url) if page_url else None
    counts = Counter(item.get("link") for item in items if item.get("link"))
    for item in items:
        legacy = item.get("unique_id")
        if legacy and not item.get("content_hash"):
            item["content_hash"] = legacy
        link = item.get("link")
        if link and link != page and counts[link] == 1:
            item["unique_id"] = hashlib.md5(
                ("link:" + link).encode("utf-8"), usedforsecurity=False
            ).hexdigest()
    return items


_JSESSIONID_RE = re.compile(r";jsessionid=[^?#/;]*", re.IGNORECASE)


def clean_url(url):
    """Remove session ids and tracking parameters, preserving everything else.

    The remaining query keeps its original order, repeated keys, blank values
    and percent-encoding byte for byte; the fragment is kept as well.
    """
    if not url:
        return url
    url = _JSESSIONID_RE.sub("", url)
    parts = urlsplit(url)
    if not parts.query:
        return url
    query = clean_urlquery(parts.query)[0]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def clean_urlquery(qs):
    """Split ``qs`` into the cleaned raw query, kept and filtered parameters.

    Returns ``(query, kept, filtered)`` where ``query`` is the original query
    string minus tracking parameters (raw segments, not re-encoded) and
    ``kept``/``filtered`` map decoded keys to lists of decoded values.
    """
    cleanable = {key.lower() for key in CLEANABLE_QUERY_KEYS}
    kept_segments = []
    kept: dict[str, list] = {}
    filtered: dict[str, list] = {}
    for segment in qs.split("&"):
        if not segment:
            continue
        raw_key, _, raw_value = segment.partition("=")
        key = unquote_plus(raw_key)
        value = unquote_plus(raw_value)
        if key.lower() in cleanable:
            filtered.setdefault(key, []).append(value)
        else:
            kept_segments.append(segment)
            kept.setdefault(key, []).append(value)
    return "&".join(kept_segments), kept, filtered


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
