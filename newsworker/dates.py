"""Turning qddate matches into plausible, timezone-aware publication times.

qddate reports the raw components it matched (day, month, year, time and, in
newer releases, a ``timezone`` token).  This module owns the policy that turns
them into an aware UTC ``datetime``: two-digit years, explicit offsets written
in the text, dates printed without a year, implausible values, and the
day/month order of numeric dates shared by a group of dates.
"""

from __future__ import annotations

import datetime as dt
import re
import threading
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

#: Earliest publication year accepted from page text.  Older values are almost
#: always numbers that merely look like dates (codes, prices, references).
MIN_PLAUSIBLE_YEAR = 1970

#: How far into the future a parsed date may lie before it is rejected.
FUTURE_TOLERANCE = dt.timedelta(days=366)

#: Dates without a year that land further than this in the future are moved to
#: the previous year ("28 Dec" read on 3 January).
NOYEAR_ROLLOVER_GRACE = dt.timedelta(days=2)

# An explicit UTC offset written right after a clock time, e.g.
# "10:00 GMT+3", "10:00:00 +0300", "10:00+03:00", "10:00 UTC-05:30", "10:00Z".
_TEXT_OFFSET_RE = re.compile(
    r"\d{1,2}:\d{2}(?::\d{2})?\s*"
    r"(?:(?P<zulu>Z)\b|(?:(?:GMT|UTC)\s*)?(?P<sign>[+-])(?P<hours>\d{1,2})(?::?(?P<minutes>\d{2}))?\b"
    r"|(?:GMT|UTC)\b)",
    re.IGNORECASE,
)

# A dateline before the date: "GENEVA, 29 July 2022", "New York – 3 May 2022",
# "Monday, January 31, 2022" (a weekday reads the same way). Up to four words,
# no digits, then a comma or a spaced dash.
_DATELINE_PREFIX_RE = re.compile(r"^[^\W\d_]+(?:[ .'’-]{1,2}[^\W\d_]+){0,3}\.?\s*(?:,|\s[-–—])\s*")

# An event span leading the date, "21-22 July 2022": the first day is the date.
_DAY_RANGE_RE = re.compile(r"^(\d{1,2})\s*[-–—]\s*\d{1,2}(?=\s+[^\W\d_])")

#: Longer text is prose, not a date line; it is not worth a second match.
MAX_DATELINE_CHARS = 64

#: ISO 639-1 codes that qddate spells differently.
QDDATE_LANGUAGE_CODES = {"cs": "cz"}

#: US month-first numeric dates contain no words but are filed under English in
#: qddate. Every language's parser keeps them, so a date without letters never
#: needs the general parser.
_WORDLESS_ENGLISH_PATTERNS = frozenset({"dt:date:date_usa", "dt:date:date_usa_1"})

_local = threading.local()


def qddate_language(language: str | None) -> str | None:
    """qddate's code for ``language`` (a BCP 47 tag such as ``cs`` or ``en-US``).

    Returns ``None`` when the tag is empty or qddate has no month names for it.
    """
    if not language:
        return None
    from qddate.patterns import SUPPORTED_LANGUAGES

    primary = re.split(r"[-_]", str(language).strip(), maxsplit=1)[0].lower()
    code = QDDATE_LANGUAGE_CODES.get(primary, primary)
    return code if code in SUPPORTED_LANGUAGES else None


def _language_patterns(language: str) -> list[dict[str, Any]]:
    from qddate.patterns import ALL_PATTERNS

    return [
        pattern
        for pattern in ALL_PATTERNS
        if pattern.get("language") in (None, language)
        or pattern["key"] in _WORDLESS_ENGLISH_PATTERNS
    ]


def thread_date_parser(language: str | None = None) -> Any:
    """Return this thread's qddate parser, building it on first use.

    Without ``language`` the parser knows every language qddate supports. With
    a qddate code from :func:`qddate_language` it knows that language's month
    and weekday names plus every pattern without words (numeric dates), so a
    page's own dates are tried against a small fraction of the patterns.

    Building a ``DateParser(generate=True)`` costs tens of milliseconds, so a
    parser is shared by every request a thread serves instead of being rebuilt
    per request.  Pattern sessions are opened and closed by
    :meth:`newsworker.runtime.ExtractionContext.narrowed_dates`, so a narrowed
    pattern set never leaks between requests.
    """
    parsers = getattr(_local, "parsers", None)
    if parsers is None:
        parsers = _local.parsers = {}
    parser = parsers.get(language)
    if parser is None:
        from qddate import DateParser

        if language is None:
            parser = DateParser(generate=True)
        else:
            if qddate_language(language) != language:
                raise ValueError(f"qddate has no date patterns for {language!r}")
            parser = DateParser(generate=True, patterns=_language_patterns(language))
        parsers[language] = parser
    return parser


def has_letters(text: str) -> bool:
    """Whether ``text`` has a letter; without one only numeric patterns can match."""
    return any(char.isalpha() for char in text)


@dataclass(frozen=True)
class DateReading:
    """One text read as a publication date, with the evidence behind it."""

    #: qddate pattern key, ``"fuzzy"`` for relative dates, ``"html:time"``.
    key: str
    #: The text as shown on the page.
    text: str
    #: Aware UTC publication time.
    value: dt.datetime
    #: The qddate match; ``None`` for relative dates and ``<time datetime>``.
    match: Mapping[str, Any] | None = None
    #: The text qddate read: ``text`` without a leading dateline or day span.
    matched_text: str | None = None
    #: qddate code of the parser that read it; ``None`` for all languages.
    parser_language: str | None = None
    #: ``"dmy"`` or ``"mdy"`` for a numeric day-month date, else ``None``.
    order: str | None = None
    #: Read again in the order chosen for its group of dates.
    reordered: bool = False

    @property
    def pattern(self) -> Mapping[str, Any]:
        return self.match["pattern"] if self.match else {"key": self.key}

    def as_tuple(self) -> tuple[bool, str, Mapping[str, Any], str, dt.datetime]:
        """The ``(matched, key, pattern, text, date)`` tuple of ``match_text``."""
        return True, self.key, self.pattern, self.text, self.value


#: Locales whose numeric dates put the month first (``05/13/2022``).
MONTH_FIRST_LOCALES = frozenset({"en-us"})

_DATE_FIELDS = ("day", "month", "year")


def _numeric_fields(match: Mapping[str, Any]) -> list[str] | None:
    """Day, month and year in printed order for a numeric date, else ``None``."""
    pattern = match.get("pattern") or {}
    basekey = pattern.get("basekey", pattern.get("key"))
    if pattern.get("language") is not None and basekey not in _WORDLESS_ENGLISH_PATTERNS:
        return None  # a month name
    values = match.get("values") or {}
    # ParseResults iterates its tokens; ``keys()`` gives the names in printed order.
    fields = [key for key in values.keys() if key in _DATE_FIELDS]  # noqa: SIM118
    if len(fields) < 2 or fields[0] == "year" or "month" not in fields[:2]:
        return None
    return fields


def numeric_order(match: Mapping[str, Any] | None) -> str | None:
    """``"dmy"`` or ``"mdy"`` for a numeric day-month qddate match.

    Dates with a month name, year-first dates (``2022-05-06``) and anything
    that is not a qddate match have no order.
    """
    fields = _numeric_fields(match) if match else None
    if fields is None:
        return None
    return "dmy" if fields[0] == "day" else "mdy"


def leading_numbers(match: Mapping[str, Any]) -> tuple[int, int] | None:
    """The first and second number of a numeric day-month date, as printed."""
    fields = _numeric_fields(match)
    if fields is None:
        return None
    values = match["values"]
    try:
        return int(values[fields[0]]), int(values[fields[1]])
    except (TypeError, ValueError):
        return None


def is_ambiguous(match: Mapping[str, Any] | None) -> bool:
    """Whether a numeric date reads as two different dates (``05/06/2022``)."""
    numbers = leading_numbers(match) if match else None
    return numbers is not None and max(numbers) <= 12 and numbers[0] != numbers[1]


@dataclass(frozen=True)
class DateOrder:
    """The day/month order chosen for a group of dates, and why."""

    #: ``"dmy"``, ``"mdy"``, or ``None`` when the group has no numeric
    #: day-month dates or its dates contradict each other.
    order: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"order": self.order, "reason": self.reason}


def choose_date_order(
    readings: Iterable[DateReading | None], locale: str | None = None
) -> DateOrder:
    """Pick one day/month order for the numeric dates a page prints together.

    A date whose first number is above 12 can only start with the day, one
    whose second number is above 12 only with the month; one such date
    decides for the whole group. Ambiguous groups follow the page ``locale``:
    ``en-US`` puts the month first, anything else the day.
    """
    day_first = month_first = None
    numeric = False
    for reading in readings:
        if reading is None or reading.match is None:
            continue
        numbers = leading_numbers(reading.match)
        if numbers is None:
            continue
        numeric = True
        if numbers[0] > 12 and day_first is None:
            day_first = reading.text
        elif numbers[1] > 12 and month_first is None:
            month_first = reading.text
    if day_first and month_first:
        return DateOrder(None, f"contradicting dates {day_first!r} and {month_first!r}")
    if day_first:
        return DateOrder("dmy", f"{day_first!r} starts with a day above 12")
    if month_first:
        return DateOrder("mdy", f"{month_first!r} has a day above 12 in second place")
    if not numeric:
        return DateOrder(None, "no numeric day-month dates")
    tag = str(locale or "").strip().replace("_", "-").lower()
    if tag in MONTH_FIRST_LOCALES:
        return DateOrder("mdy", f"ambiguous dates, page locale {locale}")
    if tag:
        return DateOrder("dmy", f"ambiguous dates, page locale {locale}")
    return DateOrder("dmy", "ambiguous dates, day first by default")


def _offset_from_token(token: Any) -> dt.timezone | None:
    text = str(token).strip()
    if not text:
        return None
    sign = -1 if text.startswith("-") else 1
    digits = text.lstrip("+-").zfill(4)
    if not digits.isdigit() or len(digits) != 4:
        return None
    hours, minutes = int(digits[:2]), int(digits[2:])
    if hours > 23 or minutes > 59:
        return None
    return dt.timezone(sign * dt.timedelta(hours=hours, minutes=minutes))


def offset_from_text(text: str | None) -> dt.timezone | None:
    """Return the UTC offset written after a clock time in ``text``, if any."""
    if not text:
        return None
    match = _TEXT_OFFSET_RE.search(text)
    if match is None:
        return None
    if match.group("zulu") or match.group("sign") is None:
        return dt.timezone.utc
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes") or 0)
    if hours > 23 or minutes > 59:
        return None
    sign = -1 if match.group("sign") == "-" else 1
    return dt.timezone(sign * dt.timedelta(hours=hours, minutes=minutes))


def date_text_variants(text: str | None) -> Iterator[str]:
    """Rewrites of ``text`` that qddate may match when ``text`` itself does not.

    Press releases put a place (or a weekday) before the date and event pages
    print day spans; qddate only matches dates at the start of the text. Yields
    the text with a leading dateline removed, then with a day span reduced to
    its first day, each only when it differs from what came before.
    """
    if not text or len(text) > MAX_DATELINE_CHARS:
        return
    current = text
    for pattern, replacement in ((_DATELINE_PREFIX_RE, ""), (_DAY_RANGE_RE, r"\1")):
        rewritten = pattern.sub(replacement, current, count=1)
        if rewritten != current and rewritten:
            current = rewritten
            yield current


def expand_two_digit_year(year: int, now: dt.datetime) -> int:
    """Map a two-digit year to the closest century that is not in the future."""
    candidate = 2000 + year
    return candidate if candidate <= now.year + 1 else 1900 + year


def is_plausible(value: dt.datetime, now: dt.datetime) -> bool:
    return value.year >= MIN_PLAUSIBLE_YEAR and value <= now + FUTURE_TOLERANCE


def build_match_datetime(
    match: Mapping[str, Any],
    text: str | None,
    *,
    now: dt.datetime,
    default_timezone: str = "UTC",
) -> dt.datetime | None:
    """Convert a qddate ``match()`` result into an aware UTC datetime.

    Returns ``None`` when the components do not form a valid, plausible date.
    """
    pattern = match.get("pattern") or {}
    values = match.get("values") or {}
    zone = ZoneInfo(default_timezone)
    local_now = now.astimezone(zone)
    parts = {"year": 0, "month": 0, "day": 0}
    offset = None
    for key, value in values.items():
        if key == "timezone":
            offset = _offset_from_token(value)
            continue
        try:
            parts[key] = int(value)
        except (TypeError, ValueError):
            return None
    no_year = bool(pattern.get("noyear"))
    if no_year:
        parts["year"] = local_now.year
    elif 0 <= parts["year"] < 100:
        parts["year"] = expand_two_digit_year(parts["year"], local_now)
    try:
        naive = dt.datetime(
            parts["year"],
            parts["month"],
            parts["day"],
            parts.get("hour", 0),
            parts.get("minute", 0),
            parts.get("second", 0),
        )
    except (TypeError, ValueError):
        return None
    if offset is None and ":time" in str(pattern.get("key", "")):
        offset = offset_from_text(text)
    value = naive.replace(tzinfo=offset or zone)
    if no_year and value > now + NOYEAR_ROLLOVER_GRACE:
        try:
            value = value.replace(year=value.year - 1)
        except ValueError:  # 29 February
            return None
    value = value.astimezone(dt.timezone.utc)
    if not is_plausible(value, now):
        return None
    return value
