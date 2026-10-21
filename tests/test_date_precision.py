"""Publication dates carry their precision; calendar days keep their day (N3)."""

import csv
import datetime as dt
import io
import json

import pytest
from lxml.html import fromstring

from newsworker.dates import anchor_day, clock_precision, read_datetime_attr
from newsworker.explain import explain, to_html, to_text
from newsworker.extractor import FeedExtractor
from newsworker.formats import content_fingerprint, format_feed
from newsworker.native import parse_native_feed
from newsworker.runtime import ExtractionContext
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.structured import extract_structured_items, merge_structured_dates

UTC = dt.timezone.utc
NOW = dt.datetime(2022, 5, 6, 12, 0, tzinfo=UTC)
MSK = "Europe/Moscow"


def _read(text, timezone=MSK):
    extractor = FeedExtractor()
    context = ExtractionContext(clock=lambda: NOW, default_timezone=timezone)
    with extractor.activate_context(context):
        return extractor.read_text(text)


@pytest.mark.parametrize(
    ("text", "value", "precision"),
    [
        ("5 мая 2022", dt.datetime(2022, 5, 5, tzinfo=UTC), "day"),
        ("05.05.2022", dt.datetime(2022, 5, 5, tzinfo=UTC), "day"),
        ("5 мая 2022, 12:30", dt.datetime(2022, 5, 5, 9, 30, tzinfo=UTC), "minute"),
        ("2022-05-05 10:00:30", dt.datetime(2022, 5, 5, 7, 0, 30, tzinfo=UTC), "second"),
        ("2022-05-05 10:00:00 +0000", dt.datetime(2022, 5, 5, 10, 0, tzinfo=UTC), "second"),
        ("вчера", dt.datetime(2022, 5, 5, tzinfo=UTC), "day"),
        ("3 дня назад", dt.datetime(2022, 5, 3, tzinfo=UTC), "day"),
        ("вчера в 14:30", dt.datetime(2022, 5, 5, 11, 30, tzinfo=UTC), "minute"),
        ("3 часа назад", dt.datetime(2022, 5, 6, 9, 0, tzinfo=UTC), "minute"),
        ("только что", NOW, "minute"),
    ],
)
def test_text_dates_carry_their_precision(text, value, precision):
    reading = _read(text)
    assert (reading.value, reading.precision) == (value, precision)


def test_a_calendar_day_is_not_moved_across_midnight():
    # Before: 00:00 in UTC+3 became 4 May, 21:00 UTC.
    for timezone in ("UTC", MSK, "America/Los_Angeles", "Pacific/Kiritimati"):
        assert _read("5 мая 2022", timezone).value.date() == dt.date(2022, 5, 5)


def test_relative_days_use_the_site_calendar():
    late = dt.datetime(2022, 5, 5, 22, 30, tzinfo=UTC)  # already 6 May in Moscow
    extractor = FeedExtractor()
    context = ExtractionContext(clock=lambda: late, default_timezone=MSK)
    with extractor.activate_context(context):
        assert extractor.read_text("today").value == dt.datetime(2022, 5, 6, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "value", "precision"),
    [
        ("2022-05-05", dt.datetime(2022, 5, 5, tzinfo=UTC), "day"),
        ("2022-05-05T10:00+03:00", dt.datetime(2022, 5, 5, 7, 0, tzinfo=UTC), "minute"),
        ("2022-05-05T10:00:00Z", dt.datetime(2022, 5, 5, 10, 0, tzinfo=UTC), "second"),
        ("2022-05-05T10:00:00", dt.datetime(2022, 5, 5, 7, 0, tzinfo=UTC), "second"),
    ],
)
def test_machine_readable_dates(raw, value, precision):
    assert read_datetime_attr(raw, MSK) == (value, precision)
    extractor = FeedExtractor()
    with extractor.activate_context(ExtractionContext(default_timezone=MSK)):
        reading = extractor.read_date(fromstring(f'<time datetime="{raw}">5 May</time>'))
    assert (reading.key, reading.value, reading.precision) == ("html:time", value, precision)


def test_clock_precision_and_anchor_day():
    assert clock_precision("Thu, 05 May 2022 10:00:30 +0000") == "second"
    assert clock_precision("Thu, 05 May 2022 10:00 GMT") == "minute"
    assert clock_precision("2022-05-05") == "day"
    assert clock_precision(None) == "day"
    late = dt.datetime(2022, 5, 5, 22, 30, tzinfo=UTC)
    assert anchor_day(late) == dt.datetime(2022, 5, 5, tzinfo=UTC)
    assert anchor_day(late, MSK) == dt.datetime(2022, 5, 6, tzinfo=UTC)


_PAGE = """<html lang="ru"><head><script type="application/ld+json">
{"@type": "ItemList", "itemListElement": [
 {"@type": "ListItem", "item": {"@type": "NewsArticle", "url": "/news/0",
  "headline": "Первая новость дня", "datePublished": "2022-05-05T10:15:00+03:00"}}]}
</script></head><body><ul class="news">
<li class="item"><h3><a href="/news/0">Первая новость дня</a></h3><span>5 мая 2022</span></li>
<li class="item"><h3><a href="/news/1">Вторая новость дня</a></h3><span>4 мая 2022</span></li>
<li class="item"><h3><a href="/news/2">Третья новость дня</a></h3><span>3 мая 2022, 18:05</span></li>
</ul></body></html>"""


def _service(tmp_path, timezone=MSK):
    settings = Settings(cache_dir=str(tmp_path), respect_robots=False, default_timezone=timezone)
    return FeedService(
        settings=settings, use_cache=False, plugins=[], bridges=[], clock=lambda: NOW
    )


def _items(tmp_path, structured=True):
    service = _service(tmp_path)
    service.settings.structured_data = structured
    feed = service.get_feed("https://example.ru/news", data=_PAGE.encode())
    return feed, {item["link"].rsplit("/", 1)[1]: item for item in feed["items"]}


def test_spec_items_carry_precision_and_keep_their_day(tmp_path):
    _feed, items = _items(tmp_path, structured=False)
    assert items["0"]["pubdate"] == dt.datetime(2022, 5, 5, tzinfo=UTC)
    assert items["0"]["date_precision"] == "day"
    assert items["2"]["pubdate"] == dt.datetime(2022, 5, 3, 15, 5, tzinfo=UTC)
    assert items["2"]["date_precision"] == "minute"


def test_dynamic_items_carry_precision():
    extractor = FeedExtractor()
    context = ExtractionContext(clock=lambda: NOW, default_timezone=MSK)
    feed, _session = extractor.get_feed(
        "https://example.ru/news", data=_PAGE.encode(), context=context
    )
    by_day = {item["pubdate"].day: item["date_precision"] for item in feed["items"]}
    assert by_day == {5: "day", 4: "day", 3: "minute"}


def test_structured_time_sharpens_a_calendar_day_in_the_site_timezone(tmp_path):
    _feed, items = _items(tmp_path)
    # 10:15 Moscow is 07:15 UTC on the same day.
    assert items["0"]["pubdate"] == dt.datetime(2022, 5, 5, 7, 15, tzinfo=UTC)
    assert items["0"]["date_precision"] == "second"
    assert items["1"]["date_precision"] == "day"


def test_structured_items_and_merge_rules():
    document = fromstring(_PAGE)
    [structured] = extract_structured_items(document, "https://example.ru/", default_timezone=MSK)
    assert structured["date_precision"] == "second"
    day = {"link": structured["link"], "pubdate": dt.datetime(2022, 5, 4, tzinfo=UTC)}
    assert merge_structured_dates([dict(day, date_precision="day")], [structured], MSK) == 0
    exact = {
        "link": structured["link"],
        "pubdate": structured["pubdate"],
        "date_precision": "minute",
    }
    assert merge_structured_dates([dict(exact)], [structured], MSK) == 0


def test_native_feed_precision():
    json_feed = json.dumps(
        {
            "version": "https://jsonfeed.org/version/1.1",
            "title": "t",
            "items": [
                {"id": "1", "url": "https://e.org/1", "date_published": "2022-05-05"},
                {"id": "2", "url": "https://e.org/2", "date_published": "2022-05-05T10:00:00Z"},
            ],
        }
    ).encode()
    items = parse_native_feed(json_feed, "https://e.org/feed.json", default_timezone=MSK)["items"]
    assert [(i["pubdate"], i["date_precision"]) for i in items] == [
        (dt.datetime(2022, 5, 5, tzinfo=UTC), "day"),
        (dt.datetime(2022, 5, 5, 10, tzinfo=UTC), "second"),
    ]
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><link>https://e.org/a</link><title>a</title><pubDate>Thu, 05 May 2022 10:00:00 +0300</pubDate></item>
</channel></rss>"""
    [item] = parse_native_feed(rss, "https://e.org/rss")["items"]
    assert item["date_precision"] == "second"


def _day_feed():
    return {
        "title": "t",
        "link": "https://e.org/",
        "description": "t",
        "language": "ru",
        "items": [
            {
                "title": "Day item",
                "description": "Day item",
                "link": "https://e.org/1",
                "unique_id": "1",
                "pubdate": dt.datetime(2022, 5, 5, tzinfo=UTC),
                "date_precision": "day",
            },
            {
                "title": "Timed item",
                "description": "Timed item",
                "link": "https://e.org/2",
                "unique_id": "2",
                "pubdate": dt.datetime(2022, 5, 5, 7, 15, tzinfo=UTC),
                "date_precision": "minute",
            },
        ],
    }


def test_outputs_keep_the_day_and_state_the_precision():
    feed = _day_feed()
    as_json = json.loads(format_feed(feed, fmt="json"))
    assert as_json["items"][0]["pubdate"] == "2022-05-05T00:00:00+00:00"
    assert as_json["items"][0]["date_precision"] == "day"
    json_feed = json.loads(format_feed(feed, fmt="jsonfeed"))
    assert json_feed["items"][0]["date_published"] == "2022-05-05T00:00:00+00:00"
    assert json_feed["items"][0]["_newsworker"] == {"date_precision": "day"}
    assert "_newsworker" not in json_feed["items"][1]
    assert "Thu, 05 May 2022 00:00:00 +0000" in format_feed(feed, fmt="rss")
    assert "2022-05-05T00:00:00+00:00" in format_feed(feed, fmt="atom")
    rows = list(csv.DictReader(io.StringIO(format_feed(feed, fmt="csv"))))
    assert [row["date_precision"] for row in rows] == ["day", "minute"]
    markdown = format_feed(feed, fmt="markdown")
    assert "**2022-05-05** —" in markdown and "2022-05-05T07:15:00+00:00" in markdown


def test_fingerprint_follows_a_known_precision():
    feed = _day_feed()
    before = content_fingerprint(feed)
    feed["items"][0]["date_precision"] = "minute"
    assert content_fingerprint(feed) != before
    for item in feed["items"]:
        del item["date_precision"]
    unknown = content_fingerprint(feed)
    feed["items"][0]["date_precision"] = None
    assert content_fingerprint(feed) == unknown


def test_explain_shows_the_precision(tmp_path):
    report = explain(_service(tmp_path), "https://example.ru/news", data=_PAGE.encode())
    text = to_text(report)
    assert "(day)" in text and "(second)" in text
    assert "2022-05-04 (day)" in text
    assert "2022-05-04 (day)" in to_html(report)
    assert {item["date_precision"] for item in report.items} == {"day", "second", "minute"}
