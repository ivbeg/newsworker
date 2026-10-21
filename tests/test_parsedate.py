"""`newsworker parsedate` reads dates the way extraction does (N7)."""

import datetime as dt
import json

import pytest
from typer.testing import CliRunner

from newsworker.core import app
from newsworker.explain import explain_date
from newsworker.extractor import FeedExtractor
from newsworker.runtime import ExtractionContext

runner = CliRunner()
NOW = "2022-05-06T12:00:00+00:00"


@pytest.fixture(autouse=True)
def _no_user_settings(monkeypatch, tmp_path):
    monkeypatch.setattr("newsworker.settings.DEFAULT_CONFIG_PATH", str(tmp_path / "none.yaml"))
    monkeypatch.delenv("NEWSWORKER_DEFAULT_TIMEZONE", raising=False)
    monkeypatch.delenv("NEWSWORKER_DEFAULT_LANGUAGE", raising=False)


def _json(*args):
    result = runner.invoke(app, ["parsedate", *args, "--json", "--now", NOW])
    return result.exit_code, json.loads(result.stdout)


def test_dateline_goes_through_the_extraction_rewrites():
    code, report = _json("GENEVA, 29 July 2022")
    assert code == 0
    assert report["matched_text"] == "29 July 2022"
    assert report["utc"] == "2022-07-29T00:00:00+00:00"
    assert report["precision"] == "day" and report["offset"] is None


def test_relative_dates_use_now():
    code, report = _json("3 hours ago")
    assert code == 0 and report["source"] == "relative"
    assert report["utc"] == "2022-05-06T09:00:00+00:00"
    assert report["precision"] == "minute"


def test_timezone_and_written_offsets():
    _code, local = _json("2022-05-05 10:00", "--timezone", "Europe/Moscow")
    assert local["utc"] == "2022-05-05T07:00:00+00:00"
    assert (local["offset"], local["offset_source"]) == ("+03:00", "timezone")
    _code, written = _json("2022-05-05 10:00 +0200", "--timezone", "Europe/Moscow")
    assert written["utc"] == "2022-05-05T08:00:00+00:00"
    assert (written["offset"], written["offset_source"]) == ("+02:00", "text")


def test_language_and_day_month_order():
    _code, us = _json("05/06/2022", "--language", "en-US")
    assert us["utc"].startswith("2022-05-06")
    assert (us["order"], us["reordered"], us["pattern"]) == ("mdy", True, "dt:date:date_usa")
    assert "en-US" in us["order_reason"]
    _code, other = _json("05/06/2022")
    assert other["utc"].startswith("2022-06-05") and other["order"] == "dmy"
    _code, ru = _json("5 мая 2022", "--language", "ru")
    assert (ru["parser_language"], ru["pattern_language"], ru["page_language"]) == (
        "ru",
        "ru",
        "ru",
    )
    _code, numeric = _json("05.06.2022", "--language", "ru")
    assert numeric["pattern_language"] is None


def test_text_output_names_pattern_language_offset_and_utc():
    result = runner.invoke(
        app, ["parsedate", "5 мая 2022, 12:30", "--timezone", "Europe/Moscow", "--language", "ru"]
    )
    assert result.exit_code == 0
    out = result.stdout
    assert "pattern:" in out and "(ru)" in out
    assert "parser:    ru" in out
    assert "offset:    +03:00 (Europe/Moscow)" in out
    assert "utc:       2022-05-05T09:30:00+00:00" in out


@pytest.mark.parametrize("text", ["nonsense", "01.01.1901", "Topic 3"])
def test_non_dates_exit_with_one(text):
    result = runner.invoke(app, ["parsedate", text])
    assert result.exit_code == 1 and "No date found" in result.stderr
    code, report = _json(text)
    assert code == 1 and report["matched"] is False


def test_settings_default_timezone_applies(monkeypatch):
    monkeypatch.setenv("NEWSWORKER_DEFAULT_TIMEZONE", "Europe/Moscow")
    _code, report = _json("2022-05-05 10:00")
    assert report["timezone"] == "Europe/Moscow"
    assert report["utc"] == "2022-05-05T07:00:00+00:00"


@pytest.mark.parametrize(
    "args", [["--timezone", "Mars/Base"], ["--now", "yesterday"]], ids=["timezone", "now"]
)
def test_invalid_options(args):
    result = runner.invoke(app, ["parsedate", "5 May 2022", *args])
    assert result.exit_code == 2


def test_naive_now_is_read_in_the_timezone():
    result = runner.invoke(
        app,
        [
            "parsedate",
            "1 hour ago",
            "--json",
            "--now",
            "2022-05-06T12:00",
            "--timezone",
            "Asia/Tokyo",
        ],
    )
    assert json.loads(result.stdout)["utc"] == "2022-05-06T02:00:00+00:00"


@pytest.mark.parametrize(
    "text",
    ["5 мая 2022", "GENEVA, 29 July 2022", "21-22 July 2022", "вчера в 14:30", "16.10.26", "x 1"],
)
def test_same_answer_as_extraction(text):
    now = dt.datetime.fromisoformat(NOW)
    report = explain_date(text, now=now, timezone="Europe/Moscow")
    extractor = FeedExtractor()
    context = ExtractionContext(clock=lambda: now, default_timezone="Europe/Moscow")
    with extractor.activate_context(context):
        reading = extractor.read_text(text)
    assert report["matched"] is (reading is not None)
    if reading is not None:
        assert report["utc"] == reading.value.isoformat()
        assert report["pattern"] == reading.key
