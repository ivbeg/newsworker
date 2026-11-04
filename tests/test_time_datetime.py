"""``<time datetime>`` elements whose visible text shows no date.

Listings such as ``<time datetime="2026-11-04T12:51"></time>`` (an icon, CSS
or JavaScript draws the date) or ``<time datetime="...">recently</time>`` carry
the date only in the attribute. Dynamic extraction, spec analysis and
``explain`` read it from there.
"""

import datetime

import pytest

from newsworker.explain import explain
from newsworker.extractor import FeedExtractor
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.spec import FeedSpec, SpecAnalyzer, SpecExtractor

URL = "https://news.example.com/news/"
TITLES = [
    "Правительство утвердило программу развития регионального транспорта",
    "Центробанк сохранил ключевую ставку на прежнем уровне",
    "В Москве открылась международная выставка цифровых технологий",
    "Минздрав обновил рекомендации по сезонной вакцинации",
    "Сборная завоевала золото на чемпионате мира по плаванию",
]


def listing(inner, datetime_attr=True):
    """Five news items; item ``i`` is dated 2026-11-04 12:(51 - i) in the attribute."""
    rows = []
    for i, title in enumerate(TITLES):
        if datetime_attr is True:
            attr = f' datetime="2026-11-04T12:{51 - i:02d}"'
        elif datetime_attr is None:
            attr = ""
        else:
            attr = f' datetime="{datetime_attr}"'
        rows.append(
            f'<div class="timeline__item"><time{attr}>{inner}</time>'
            f'<a href="/news/{1000 + i}"><h3>{title}</h3></a></div>'
        )
    return (
        '<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><title>Новости</title>'
        '</head><body><h1>Новости</h1><div class="timeline">'
        + "".join(rows)
        + "</div></body></html>"
    ).encode()


EXPECTED = [
    datetime.datetime(2026, 11, 4, 12, 51 - i, tzinfo=datetime.timezone.utc) for i in range(5)
]

ATTRIBUTE_ONLY = {
    "empty": "",
    "non-date text": "недавно",
    "icon only": '<i class="icon-clock"></i>',
}


@pytest.mark.parametrize("inner", ATTRIBUTE_ONLY.values(), ids=ATTRIBUTE_ONLY.keys())
def test_dynamic_extraction_reads_the_datetime_attribute(inner):
    feed, _ = FeedExtractor(filtered_text_length=150).get_feed(URL, data=listing(inner))
    items = feed["items"]
    assert [item["pubdate"] for item in items] == EXPECTED
    assert all(item["date_precision"] == "minute" for item in items)
    assert [item["title"] for item in items] == TITLES
    assert items[0]["link"] == "https://news.example.com/news/1000"
    assert feed["cache"]["pats"] == ["html:time"]


@pytest.mark.parametrize(
    "inner, datetime_attr",
    [("недавно", None), ("", None), ("недавно", ""), ("недавно", "  ")],
    ids=["no attribute", "empty no attribute", "empty attribute", "blank attribute"],
)
def test_time_without_a_datetime_and_without_digits_is_ignored(inner, datetime_attr):
    feed, _ = FeedExtractor(filtered_text_length=150).get_feed(
        URL, data=listing(inner, datetime_attr=datetime_attr)
    )
    assert feed["items"] == []


def test_date_text_inside_the_time_still_groups_the_items():
    """Text one level below ``<time datetime>`` does not split the run of dates."""
    rows = "".join(
        f'<div class="item"><time datetime="2026-11-0{day}T09:30">'
        f'<span>{day} ноября 2026</span></time><a href="/n/{day}"><h3>{title}</h3></a></div>'
        for day, title in zip(range(5, 0, -1), TITLES, strict=True)
    )
    page = f'<html lang="ru"><body><div class="list">{rows}</div></body></html>'.encode()
    feed, _ = FeedExtractor(filtered_text_length=150).get_feed(URL, data=page)
    assert [item["pubdate"].date() for item in feed["items"]] == [
        datetime.date(2026, 11, day) for day in range(5, 0, -1)
    ]


@pytest.mark.parametrize("inner", ATTRIBUTE_ONLY.values(), ids=ATTRIBUTE_ONLY.keys())
def test_spec_reads_the_datetime_attribute_after_a_round_trip(inner):
    page = listing(inner)
    spec = SpecAnalyzer().analyze(URL, data=page)
    date_rule = spec.fields["date"]
    assert date_rule.source == "attr:datetime"
    assert date_rule.patterns == ["html:time"]

    cached = FeedSpec.from_yaml(spec.to_yaml())
    feed = SpecExtractor().extract(URL, cached, data=page)
    assert [item["pubdate"] for item in feed["items"]] == EXPECTED
    assert [item["title"] for item in feed["items"]] == TITLES


def test_service_uses_an_inferred_spec(tmp_path):
    service = FeedService(Settings(cache_dir=str(tmp_path)), use_cache=False)
    context = service.new_context(source="file", base_url=URL)
    feed = service.get_feed(URL, data=listing(""), context=context)
    assert [item["pubdate"] for item in feed["items"]] == EXPECTED
    assert context.diagnostics.chosen_strategy == "spec"


def test_explain_shows_the_attribute_dates(tmp_path):
    service = FeedService(Settings(cache_dir=str(tmp_path)), use_cache=False)
    report = explain(service, URL, data=listing(""), source="file")
    assert len(report.items) == 5
    chosen = report.clusters[0]
    assert chosen.chosen and chosen.dates == 5
    assert chosen.patterns == ["html:time"]
    assert chosen.samples == ["2026-11-04T12:51", "2026-11-04T12:50", "2026-11-04T12:49"]
    assert report.spec_yaml and "attr:datetime" in report.spec_yaml
