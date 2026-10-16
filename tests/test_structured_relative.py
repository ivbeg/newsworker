import datetime as dt
import json

import pytest
from lxml.html import fromstring

from newsworker.relative import looks_relative, parse_relative
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.structured import extract_structured_items, merge_structured_dates

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
BASE = "https://news.example/list"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3 hours ago", NOW - dt.timedelta(hours=3)),
        ("an hour ago", NOW - dt.timedelta(hours=1)),
        ("2 дня назад", NOW - dt.timedelta(days=2)),
        ("час назад", NOW - dt.timedelta(hours=1)),
        ("5 хвилин тому", NOW - dt.timedelta(minutes=5)),
        ("vor 3 Tagen", NOW - dt.timedelta(days=3)),
        ("vor einer Stunde", NOW - dt.timedelta(hours=1)),
        ("il y a 2 semaines", NOW - dt.timedelta(weeks=2)),
        ("hace un día", NOW - dt.timedelta(days=1)),
        ("2 giorni fa", NOW - dt.timedelta(days=2)),
        ("há 4 horas", NOW - dt.timedelta(hours=4)),
        ("3 dias atrás", NOW - dt.timedelta(days=3)),
        ("вчера", NOW - dt.timedelta(days=1)),
        ("gestern", NOW - dt.timedelta(days=1)),
        ("Только что", NOW),
    ],
)
def test_relative_phrases(text, expected):
    assert looks_relative(text)
    assert parse_relative(text, now=NOW) == expected


def test_yesterday_with_clock_time_uses_the_site_timezone():
    value = parse_relative("вчера в 14:30", now=NOW, default_timezone="Europe/Moscow")
    assert value == dt.datetime(2026, 10, 15, 11, 30, tzinfo=UTC)
    assert parse_relative("hier à 18h30", now=NOW) == dt.datetime(2026, 10, 15, 18, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "text", ["today's agenda", "Yesterday Tonight special", "in 3 days", "42 items"]
)
def test_relative_parser_rejects_non_dates(text):
    assert parse_relative(text, now=NOW) is None


def _page(head="", body=""):
    return fromstring(f"<html><head><title>T</title>{head}</head><body>{body}</body></html>")


def test_json_ld_item_list_and_graph():
    graph = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "CollectionPage", "url": BASE},
            {
                "@type": "ItemList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "item": {
                            "@type": "NewsArticle",
                            "headline": "One",
                            "url": "/n/1",
                            "datePublished": "2026-10-15T09:00:00+03:00",
                            "author": [{"@type": "Person", "name": "Ann"}],
                        },
                    },
                    {"@type": "ListItem", "url": "/n/2", "name": "Two"},
                ],
            },
            {
                "@type": ["BlogPosting"],
                "headline": "Three",
                "mainEntityOfPage": {"@id": "/n/3"},
                "datePublished": "2026-10-14",
                "image": {"url": "/i.png"},
            },
            {"@type": "NewsArticle", "headline": "Bad", "url": "javascript:alert(1)"},
        ],
    }
    document = _page(
        f'<script type="application/ld+json">{json.dumps(graph)}</script>'
        '<script type="application/ld+json">{broken</script>'
    )
    items = extract_structured_items(document, BASE)
    assert [item["title"] for item in items] == ["One", "Two", "Three"]
    assert items[0]["link"] == "https://news.example/n/1"
    assert items[0]["pubdate"] == dt.datetime(2026, 10, 15, 6, 0, tzinfo=UTC)
    assert items[0]["author"] == "Ann"
    assert items[1]["pubdate"] is None
    assert items[2]["image"] == "https://news.example/i.png"


def test_microdata_ignores_nested_item_properties():
    document = _page(
        body="""
    <article itemscope itemtype="https://schema.org/NewsArticle">
      <h2 itemprop="headline"><a itemprop="url" href="/m/1">Micro one</a></h2>
      <time itemprop="datePublished" datetime="2026-10-12T08:00:00Z">12 Oct</time>
      <div itemprop="author" itemscope itemtype="https://schema.org/Person">
        <span itemprop="name">Bob</span><a itemprop="url" href="/people/bob">Bob</a>
      </div>
    </article>"""
    )
    items = extract_structured_items(document, BASE)
    assert len(items) == 1
    assert items[0]["link"] == "https://news.example/m/1"
    assert items[0]["pubdate"] == dt.datetime(2026, 10, 12, 8, 0, tzinfo=UTC)


def test_merge_sharpens_same_day_dates_and_fills_missing():
    items = [
        {"link": "https://a/1", "pubdate": dt.datetime(2026, 10, 15, tzinfo=UTC)},
        {"link": "https://a/2", "pubdate": None},
        {"link": "https://a/3", "pubdate": dt.datetime(2026, 10, 1, tzinfo=UTC)},
    ]
    structured = [
        {
            "link": "https://a/1",
            "pubdate": dt.datetime(2026, 10, 15, 9, 30, tzinfo=UTC),
            "author": "A",
        },
        {"link": "https://a/2", "pubdate": dt.datetime(2026, 10, 14, 7, 0, tzinfo=UTC)},
        {"link": "https://a/3", "pubdate": dt.datetime(2026, 10, 2, 7, 0, tzinfo=UTC)},
    ]
    assert merge_structured_dates(items, structured) == 2
    assert items[0]["pubdate"].hour == 9 and items[0]["author"] == "A"
    assert items[1]["pubdate"] == dt.datetime(2026, 10, 14, 7, 0, tzinfo=UTC)
    assert items[2]["pubdate"] == dt.datetime(2026, 10, 1, tzinfo=UTC)


def test_service_falls_back_to_structured_items(tmp_path):
    graph = {
        "@type": "ItemList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "item": {
                    "@type": "NewsArticle",
                    "headline": f"Headline number {n}",
                    "url": f"/s/{n}",
                    "datePublished": f"2026-10-1{n}T10:00:00Z",
                },
            }
            for n in range(3)
        ],
    }
    html = (
        f"<html><head><title>Structured</title><script type='application/ld+json'>"
        f"{json.dumps(graph)}</script></head><body><p>No visible dates.</p></body></html>"
    ).encode()
    service = FeedService(Settings(cache_dir=str(tmp_path)), use_cache=False)
    feed, diagnostics = service.get_feed_with_diagnostics(BASE, data=html)
    assert diagnostics.chosen_strategy == "structured"
    assert [item["link"] for item in feed["items"]] == [
        f"https://news.example/s/{n}" for n in range(3)
    ]

    disabled = FeedService(
        Settings(cache_dir=str(tmp_path), structured_data=False), use_cache=False
    )
    assert disabled.get_feed(BASE, data=html)["items"] == []
