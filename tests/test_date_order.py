"""One day/month order per group of numeric dates (N2)."""

import datetime as dt

import pytest
from lxml.html import fromstring

from newsworker.dates import choose_date_order, is_ambiguous, numeric_order
from newsworker.explain import explain, to_html, to_text
from newsworker.extractor import FeedExtractor
from newsworker.runtime import ExtractionContext
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.spec import SpecAnalyzer


def _reading(text, order=None):
    extractor = FeedExtractor()
    with extractor.activate_context(ExtractionContext()), extractor.ordered_dates(order):
        return extractor.read_text(text)


@pytest.mark.parametrize(
    ("text", "order", "ambiguous"),
    [
        ("05/06/2022", "dmy", True),
        ("05/13/2022", "mdy", False),
        ("13/05/2022", "dmy", False),
        ("05/05/2022", "dmy", False),
        ("05/06/22", "mdy", True),  # qddate reads slashed two-digit years month first
        ("05.06.2022", "dmy", True),
        ("2022-05-06", None, False),
        ("5 May 2022", None, False),
        ("3 hours ago", None, False),
    ],
)
def test_numeric_order_and_ambiguity(text, order, ambiguous):
    reading = _reading(text)
    assert reading is not None
    assert reading.order == order == numeric_order(reading.match)
    assert is_ambiguous(reading.match) is ambiguous


def _order(texts, locale=None):
    return choose_date_order([_reading(text) for text in texts], locale)


def test_a_day_above_12_decides_the_whole_group():
    assert _order(["05/06/2022", "13/05/2022"], "en-US").order == "dmy"
    decided = _order(["05/06/2022", "05/13/2022", "05/02/2022"])
    assert decided.order == "mdy"
    assert "05/13/2022" in decided.reason


def test_ambiguous_groups_follow_the_page_locale():
    assert _order(["05/06/2022", "05/04/2022"], "en-US").order == "mdy"
    assert _order(["05/06/2022", "05/04/2022"], "en_US").order == "mdy"
    assert _order(["05/06/2022", "05/04/2022"], "en").order == "dmy"
    assert _order(["05/06/2022", "05/04/2022"], "en-GB").order == "dmy"
    default = _order(["05/06/2022", "05/04/2022"])
    assert default.order == "dmy" and "default" in default.reason


def test_contradicting_or_non_numeric_groups_keep_each_reading():
    assert _order(["13/05/2022", "05/13/2022"]).order is None
    assert _order(["5 May 2022", "2022-05-06"]).order is None


def test_rereading_in_the_chosen_order():
    us = _reading("05/06/2022", "mdy")
    assert us.value == dt.datetime(2022, 5, 6, tzinfo=dt.timezone.utc)
    assert us.key == "dt:date:date_usa" and us.reordered
    assert _reading("05/06/22", "dmy").value.date() == dt.date(2022, 6, 5)
    with_time = _reading("05/06/2022 10:30", "mdy")
    assert with_time.value == dt.datetime(2022, 5, 6, 10, 30, tzinfo=dt.timezone.utc)
    # Unambiguous and dotted dates keep their only reading.
    assert _reading("13/05/2022", "mdy").value.date() == dt.date(2022, 5, 13)
    assert _reading("05.06.2022", "mdy").value.date() == dt.date(2022, 6, 5)


def _page(lang, dates):
    items = "".join(
        f'<li class="news-item"><h3><a href="/news/{index}">Headline number {index} of the day'
        f'</a></h3><span class="date">{date}</span></li>'
        for index, date in enumerate(dates)
    )
    attr = f' lang="{lang}"' if lang else ""
    return f'<html{attr}><body><ul class="news">{items}</ul></body></html>'.encode()


US = ["05/06/2022", "05/04/2022", "05/02/2022"]


def _dynamic_dates(data):
    feed, _session = FeedExtractor().get_feed("https://example.com/news", data=data)
    return [item["pubdate"].date() for item in feed["items"]]


def _service_dates(tmp_path, data):
    service = FeedService(
        settings=Settings(cache_dir=str(tmp_path), respect_robots=False),
        use_cache=False,
        plugins=[],
        bridges=[],
    )
    feed, diagnostics = service.get_feed_with_diagnostics("https://example.com/news", data=data)
    return [item["pubdate"].date() for item in feed["items"]], diagnostics


MAY = [dt.date(2022, 5, 6), dt.date(2022, 5, 4), dt.date(2022, 5, 2)]
DAY_FIRST = [dt.date(2022, 6, 5), dt.date(2022, 4, 5), dt.date(2022, 2, 5)]


@pytest.mark.parametrize(
    ("lang", "dates", "expected"),
    [
        ("en-US", US, MAY),
        ("en-GB", US, DAY_FIRST),
        (None, ["05/13/2022", *US[:2]], [dt.date(2022, 5, 13), *MAY[:2]]),
        ("en-US", ["13/05/2022", *US[:2]], [dt.date(2022, 5, 13), *DAY_FIRST[:2]]),
        ("ru", ["05/06/22", "04/06/22"], [dt.date(2022, 6, 5), dt.date(2022, 6, 4)]),
    ],
)
def test_dynamic_and_spec_extraction_agree_on_the_order(tmp_path, lang, dates, expected):
    data = _page(lang, dates)
    assert _dynamic_dates(data) == expected
    got, diagnostics = _service_dates(tmp_path, data)
    assert got == expected
    assert diagnostics.chosen_strategy == "spec"
    assert diagnostics.metadata["date_order"][0]["order"] in ("dmy", "mdy")


def test_analysis_keeps_the_reordered_pattern_keys():
    spec = SpecAnalyzer().analyze("https://example.com/news", data=_page("en-US", US))
    assert spec.fields["date"].patterns == ["dt:date:date_usa"]


def test_explain_shows_the_order(tmp_path):
    service = FeedService(
        settings=Settings(cache_dir=str(tmp_path), respect_robots=False),
        use_cache=False,
        plugins=[],
        bridges=[],
    )
    report = explain(service, "https://example.com/news", data=_page("en-US", US))
    chosen = next(cluster for cluster in report.clusters if cluster.chosen)
    assert chosen.date_order == "mdy" and "en-US" in chosen.date_order_reason
    assert report.date_orders and report.date_orders[0]["order"] == "mdy"
    text = to_text(report)
    assert "date order mdy" in text and "page locale en-US" in text
    assert "<b>mdy</b>" in to_html(report)


def test_explicit_language_without_region_keeps_the_page_region():
    def locale(page_lang, override):
        extractor = FeedExtractor(default_language=override)
        context = ExtractionContext()
        with extractor.activate_context(context):
            extractor.use_page_language(
                fromstring(f'<html lang="{page_lang}"><body></body></html>')
            )
        return context.date_locale, context.date_language

    assert locale("en-US", "en") == ("en-US", "en")
    assert locale("en-US", "en-GB") == ("en-GB", "en")
    assert locale("en-US", "fr") == ("fr", "fr")
    assert locale("de-DE", None) == ("de-DE", "de")
