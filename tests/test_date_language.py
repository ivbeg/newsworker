"""Tests for fuzzy relative-date parsing and language detection."""

import datetime

from lxml.html import fromstring

from newsworker.tools import (
    detect_html_language,
    looks_like_fuzzy_date,
    parse_fuzzy_date,
)


NOW = datetime.datetime(2026, 7, 4, 12, 0, 0)


def test_fuzzy_hours_ago():
    assert parse_fuzzy_date("2 hours ago", now=NOW) == NOW - datetime.timedelta(hours=2)


def test_fuzzy_minutes_and_days():
    assert parse_fuzzy_date("30 minutes ago", now=NOW) == NOW - datetime.timedelta(minutes=30)
    assert parse_fuzzy_date("3 days ago", now=NOW) == NOW - datetime.timedelta(days=3)


def test_fuzzy_yesterday_today_now():
    assert parse_fuzzy_date("yesterday", now=NOW) == NOW - datetime.timedelta(days=1)
    assert parse_fuzzy_date("today", now=NOW) == NOW
    assert parse_fuzzy_date("just now", now=NOW) == NOW


def test_fuzzy_article_form():
    assert parse_fuzzy_date("an hour ago", now=NOW) == NOW - datetime.timedelta(hours=1)
    assert parse_fuzzy_date("a week ago", now=NOW) == NOW - datetime.timedelta(weeks=1)


def test_fuzzy_embedded_in_sentence():
    assert parse_fuzzy_date("Published 5 minutes ago", now=NOW) == NOW - datetime.timedelta(minutes=5)


def test_fuzzy_returns_none_for_non_relative():
    assert parse_fuzzy_date("2024-01-01") is None
    assert parse_fuzzy_date("") is None
    assert parse_fuzzy_date(None) is None


def test_looks_like_fuzzy_date():
    assert looks_like_fuzzy_date("Posted yesterday")
    assert looks_like_fuzzy_date("3 hours ago")
    assert not looks_like_fuzzy_date("January 2024")


def test_detect_language_from_html_lang():
    doc = fromstring("<html lang='fr'><body><p>Bonjour</p></body></html>")
    assert detect_html_language(doc) == "fr"


def test_detect_language_strips_region():
    doc = fromstring("<html lang='en-US'><body></body></html>")
    assert detect_html_language(doc) == "en"


def test_detect_language_none_when_absent():
    doc = fromstring("<html><body></body></html>")
    assert detect_html_language(doc) is None
