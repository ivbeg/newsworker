import datetime as dt
import threading

import pytest

from newsworker.dates import (
    build_match_datetime,
    expand_two_digit_year,
    offset_from_text,
    thread_date_parser,
)
from newsworker.extractor import FeedExtractor
from newsworker.runtime import ExtractionContext

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def _match(text, now=NOW, timezone="UTC"):
    extractor = FeedExtractor()
    context = ExtractionContext(clock=lambda: now, default_timezone=timezone)
    with extractor.activate_context(context):
        matched, _key, _pattern, _text, value = extractor.match_text(text)
    return value if matched else None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("25/7/22", dt.datetime(2022, 7, 25, tzinfo=UTC)),
        ("16.10.26", dt.datetime(2026, 10, 16, tzinfo=UTC)),
        ("16.10.2026", dt.datetime(2026, 10, 16, tzinfo=UTC)),
    ],
)
def test_two_digit_years_resolve_to_the_nearest_past_century(text, expected):
    assert _match(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-10-16 10:00:00 +0300", dt.datetime(2026, 10, 16, 7, 0, tzinfo=UTC)),
        ("2026-10-16 10:00:00 -0500", dt.datetime(2026, 10, 16, 15, 0, tzinfo=UTC)),
        ("16 Oct 2026 10:00 GMT+3", dt.datetime(2026, 10, 16, 7, 0, tzinfo=UTC)),
    ],
)
def test_explicit_offsets_in_text_are_honoured(text, expected):
    assert _match(text) == expected


def test_offsetless_time_uses_the_default_timezone():
    value = _match("2026-10-16 10:00:00", timezone="Europe/Moscow")
    assert value == dt.datetime(2026, 10, 16, 7, 0, tzinfo=UTC)


def _noyear(day, month, now):
    match = {
        "pattern": {"key": "dt:date:noyear_1", "noyear": True},
        "values": {"day": str(day), "month": str(month)},
    }
    return build_match_datetime(match, None, now=now)


def test_date_without_year_rolls_back_over_new_year():
    january = dt.datetime(2026, 1, 3, 12, 0, tzinfo=UTC)
    assert _noyear(28, 12, january) == dt.datetime(2025, 12, 28, tzinfo=UTC)
    assert _noyear(2, 1, january) == dt.datetime(2026, 1, 2, tzinfo=UTC)


@pytest.mark.parametrize("text", ["01.01.1901", "16.10.2099"])
def test_implausible_dates_are_rejected(text):
    assert _match(text) is None


def test_offset_from_text_variants():
    assert offset_from_text("10:00+03:00") == dt.timezone(dt.timedelta(hours=3))
    assert offset_from_text("10:00 UTC-05:30") == dt.timezone(-dt.timedelta(hours=5, minutes=30))
    assert offset_from_text("10:00Z") == UTC
    assert offset_from_text("10:00 GMT") == UTC
    assert offset_from_text("Published 2026-10-16, 3 comments") is None
    assert offset_from_text("10:00 - 3 comments") is None


def test_signed_timezone_token_from_newer_qddate():
    match = {
        "pattern": {"key": "dt:date:date_9:time_2:t_right"},
        "values": {
            "year": "2026",
            "month": "10",
            "day": "16",
            "hour": "10",
            "minute": "0",
            "second": "0",
            "timezone": "-0500",
        },
    }
    assert build_match_datetime(match, None, now=NOW) == dt.datetime(
        2026, 10, 16, 15, 0, tzinfo=UTC
    )


def test_expand_two_digit_year():
    assert expand_two_digit_year(27, NOW) == 2027
    assert expand_two_digit_year(28, NOW) == 1928
    assert expand_two_digit_year(99, NOW) == 1999


def test_date_parser_is_shared_per_thread():
    first = thread_date_parser()
    assert thread_date_parser() is first
    seen = []
    worker = threading.Thread(target=lambda: seen.append(thread_date_parser()))
    worker.start()
    worker.join()
    assert seen[0] is not first


def test_cached_pattern_session_is_closed_after_failure(monkeypatch):
    extractor = FeedExtractor()
    context = ExtractionContext()

    def boom(*_args, **_kwargs):
        raise RuntimeError("parse failure")

    monkeypatch.setattr(extractor, "_build_feed", boom)
    with pytest.raises(RuntimeError):
        extractor.get_feed(
            "https://example.org/",
            data=b"<html></html>",
            cached_p=["dt:date:date_1"],
            context=context,
        )
    # A leaked session would restrict the shared parser to one pattern.
    assert _match("2026-10-16 10:00:00 +0300") is not None
