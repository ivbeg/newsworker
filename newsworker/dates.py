"""Turning qddate matches into plausible, timezone-aware publication times.

qddate reports the raw components it matched (day, month, year, time and, in
newer releases, a ``timezone`` token).  This module owns the policy that turns
them into an aware UTC ``datetime``: two-digit years, explicit offsets written
in the text, dates printed without a year, and implausible values.
"""

from __future__ import annotations

import datetime as dt
import re
import threading
from typing import Any, Iterable, Mapping, Optional
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

_local = threading.local()


def thread_date_parser() -> Any:
    """Return this thread's qddate parser, building it on first use.

    Building a ``DateParser(generate=True)`` costs tens of milliseconds, so a
    parser is shared by every request a thread serves instead of being rebuilt
    per request.  Callers must pair :func:`start_session` with
    :func:`end_session` so a narrowed pattern set never leaks between requests.
    """
    parser = getattr(_local, "parser", None)
    if parser is None:
        from qddate import DateParser

        parser = DateParser(generate=True)
        _local.parser = parser
    return parser


def start_session(parser: Any, patterns: Iterable[str]) -> None:
    """Restrict ``parser`` to ``patterns`` across qddate API generations."""
    method = getattr(parser, "start_session", None) or parser.startSession
    method(list(patterns))


def end_session(parser: Any) -> None:
    method = getattr(parser, "end_session", None) or parser.endSession
    method()


def _offset_from_token(token: Any) -> Optional[dt.timezone]:
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


def offset_from_text(text: Optional[str]) -> Optional[dt.timezone]:
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


def expand_two_digit_year(year: int, now: dt.datetime) -> int:
    """Map a two-digit year to the closest century that is not in the future."""
    candidate = 2000 + year
    return candidate if candidate <= now.year + 1 else 1900 + year


def is_plausible(value: dt.datetime, now: dt.datetime) -> bool:
    return value.year >= MIN_PLAUSIBLE_YEAR and value <= now + FUTURE_TOLERANCE


def build_match_datetime(
    match: Mapping[str, Any],
    text: Optional[str],
    *,
    now: dt.datetime,
    default_timezone: str = "UTC",
) -> Optional[dt.datetime]:
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
        naive = dt.datetime(**parts)
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
