"""Tests for fuzzy relative-date parsing and language detection."""

import datetime

from lxml.html import fromstring

from newsworker.spec import SpecAnalyzer
from newsworker.tools import (
    detect_html_language,
    detect_page_language_metadata,
    detect_text_language,
    detect_text_language_from_samples,
    normalize_language_tag,
    resolve_feed_language,
    looks_like_fuzzy_date,
    parse_fuzzy_date,
    parse_datetime_attr,
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


def test_parse_datetime_attr_iso():
    assert parse_datetime_attr("2026-07-04T20:30:32-03:00") == datetime.datetime(
        2026, 7, 4, 20, 30, 32
    )
    assert parse_datetime_attr("2026-07-04") == datetime.datetime(2026, 7, 4)


def test_parse_datetime_attr_invalid():
    assert parse_datetime_attr("") is None
    assert parse_datetime_attr("not-a-date") is None


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


def test_normalize_language_tag_handles_region_and_script():
    assert normalize_language_tag("en-US") == "en"
    assert normalize_language_tag("fr_FR") == "fr"
    assert normalize_language_tag("") is None


def test_detect_page_language_from_meta_content_language():
    doc = fromstring(
        "<html><head>"
        '<meta http-equiv="content-language" content="de-DE">'
        "</head><body></body></html>"
    )
    assert detect_page_language_metadata(doc) == "de"


def test_detect_page_language_from_og_locale():
    doc = fromstring(
        "<html><head>"
        '<meta property="og:locale" content="pt_BR">'
        "</head><body></body></html>"
    )
    assert detect_page_language_metadata(doc) == "pt"


def test_detect_text_language_cyrillic():
    assert detect_text_language("Важная новость о экономике сегодня") == "ru"


def test_detect_text_language_ukrainian():
    assert detect_text_language("Важлива новина про економіку України сьогодні") == "uk"


def test_detect_text_language_french():
    assert detect_text_language(
        "Une décision importante sur l'économie française aujourd'hui"
    ) == "fr"


def test_detect_text_language_from_samples_votes():
    samples = [
        "Важная новость о экономике сегодня",
        "Вторая важная новость о политике страны",
        "Третья важная новость о спорте и культуре",
    ]
    assert detect_text_language_from_samples(samples) == "ru"


def test_resolve_feed_language_prefers_text_over_default_en_metadata():
    doc = fromstring("<html lang='en'><body></body></html>")
    samples = [
        "Важная новость о экономике сегодня",
        "Вторая важная новость о политике страны",
    ]
    assert resolve_feed_language(document=doc, text_samples=samples) == "ru"


def test_resolve_feed_language_keeps_explicit_metadata():
    doc = fromstring("<html lang='fr'><body></body></html>")
    samples = ["Важная новость о экономике сегодня"]
    assert resolve_feed_language(document=doc, text_samples=samples) == "fr"


def test_resolve_feed_language_honors_override():
    doc = fromstring("<html lang='fr'><body></body></html>")
    assert resolve_feed_language(override="de", document=doc) == "de"


def test_resolve_feed_language_uses_content_language_header():
    doc = fromstring("<html><body></body></html>")
    assert resolve_feed_language(document=doc, content_language="es-MX") == "es"


def test_analyzer_detects_language_from_item_text():
    html = (
        "<!DOCTYPE html><html lang=\"en\"><head><title>Press</title></head><body>"
        "<main><ul>"
        "<li><span class=\"date\">03.07.2026</span>"
        "<a href=\"/a\">Важная новость о экономике страны сегодня</a></li>"
        "<li><span class=\"date\">02.07.2026</span>"
        "<a href=\"/b\">Вторая важная новость о политике региона</a></li>"
        "<li><span class=\"date\">01.07.2026</span>"
        "<a href=\"/c\">Третья важная новость о спорте и культуре</a></li>"
        "</ul></main></body></html>"
    ).encode("utf-8")
    spec = SpecAnalyzer(filtered_text_length=150).analyze(
        "https://example.com/press", data=html
    )
    assert spec.language == "ru"
