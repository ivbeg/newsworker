"""Listings split into sibling wrappers (one per hour or day) read as one listing."""

import json
import pathlib

from newsworker.explain import explain, to_html, to_text
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.spec import SpecAnalyzer, SpecExtractor

CORPUS = pathlib.Path(__file__).parent / "corpus"
URL = "https://news.example.org/ru/news/"


def _case(name):
    cases = json.loads((CORPUS / "cases.json").read_text(encoding="utf-8"))["cases"]
    case = next(case for case in cases if case["name"] == name)
    return case, (CORPUS / case["page"]).read_bytes()


def _candidates(page, url=URL):
    analyzer = SpecAnalyzer()
    document = analyzer.ext.parse_page(page)
    analyzer.ext.init_session()
    try:
        clusters = analyzer.ext.getclusters(document, url)
    finally:
        analyzer.ext.clear_session()
    return clusters, analyzer.candidate_clusters(clusters)


def _merged(candidates):
    return {path: info for path, info in candidates.items() if info.get("groups")}


def test_timeline_wrappers_merge_into_one_listing():
    case, page = _case("ru-grouped")
    clusters, candidates = _candidates(page)
    wrappers = [
        path
        for path, info in clusters.items()
        if "timeline__group" in info["snode"].get("class", "")
    ]
    assert len(wrappers) >= 2
    merged = _merged(candidates)
    assert len(merged) == 1
    (info,) = merged.values()
    assert info["snode"].get("class") == "timeline"
    # Three wrappers (one holds a single item that clustering never paired),
    # and the items placed between them.
    assert info["groups"] == 3
    assert len(info["item_roots"]) == len(case["expected"]) == 8
    assert not any(path in candidates for path in wrappers)


def test_spec_selects_every_item_with_its_headline_link():
    case, page = _case("ru-grouped-quotes")
    spec = SpecAnalyzer().analyze(URL, data=page)
    assert spec.items.selector.startswith("div.timeline__group > div")
    assert "div.timeline__smalltext" in spec.items.selector
    assert spec.items.container.endswith("/div[2]")
    assert spec.fields["link"].selector == ".//a[.//h3]"

    feed = SpecExtractor().extract(URL, spec, data=page)
    got = [(item["title"], item["link"]) for item in feed["items"]]
    assert got == [(want["title"], want["link"]) for want in case["expected"]]


def test_quotes_table_with_more_dates_per_group_loses(tmp_path):
    case, page = _case("en-grouped-quotes")
    service = FeedService(Settings(cache_dir=str(tmp_path)), use_cache=False)
    items = service.get_feed(case["url"], data=page)["items"]
    assert [item["link"] for item in items] == [want["link"] for want in case["expected"]]
    assert not any("/quotes/" in item["link"] for item in items)


def test_wrappers_with_a_different_date_place_stay_apart():
    rows = "".join(
        f'<li><span class="date">{day:02d}.10.2025</span>'
        f'<a href="/n/{day}">Headline number {day} for the list</a></li>'
        for day in range(1, 4)
    )
    nested = "".join(
        f'<li><p><span class="date">{day:02d}.10.2025</span></p>'
        f'<a href="/n/{day}">Headline number {day} for the list</a></li>'
        for day in range(4, 7)
    )
    page = (
        f'<html><body><div class="days"><ul class="day">{rows}</ul>'
        f'<ul class="day">{nested}</ul></div></body></html>'
    ).encode()
    clusters, candidates = _candidates(page)
    assert not _merged(candidates)
    assert candidates == clusters


def test_listing_without_groups_is_unchanged():
    _case_info, page = _case("en-list-long")
    clusters, candidates = _candidates(page, "https://news.example.org/en/news/")
    assert candidates == clusters


def test_selector_list_matching_undated_elements_is_not_used():
    """A bare ``div`` per direct item also matches the undated ``div`` inside it."""
    entry = (
        '<time datetime="2025-10-{d:02d}T10:00">10:00</time>'
        '<a href="/n/{d}"><h3>Headline number {d} of the timeline</h3></a>'
        "<div>Share</div>"
    )
    group = '<section class="hour">{}</section>'
    page = (
        '<html><body><div class="feed">'
        + group.format("".join(f"<article>{entry.format(d=d)}</article>" for d in (1, 2)))
        + "".join(f"<div>{entry.format(d=d)}</div>" for d in (3, 4))
        + group.format("".join(f"<article>{entry.format(d=d)}</article>" for d in (5, 6)))
        + "</div></body></html>"
    ).encode()
    clusters, candidates = _candidates(page)
    assert not _merged(candidates)


def test_explain_reports_the_merged_group(tmp_path):
    case, page = _case("ru-grouped")
    service = FeedService(Settings(cache_dir=str(tmp_path)), use_cache=False)
    report = explain(service, case["url"], data=page, source="file")
    chosen = report.clusters[0]
    assert chosen.chosen and chosen.groups == 3 and chosen.dates == 8
    assert chosen.container == "/html/body/div"
    assert not any(
        cluster.container.startswith(chosen.container + "/") for cluster in report.clusters
    )
    assert "8 dates in 3 groups" in to_text(report)
    assert "8 in 3 groups" in to_html(report)
