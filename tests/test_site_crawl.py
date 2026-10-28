"""`scan --crawl`: a bounded same-site crawl for feeds and news listings."""

import csv
import io
import json

import pytest
from typer.testing import CliRunner

from newsworker.core import app
from newsworker.fetch import HOSTS, FetchResult
from newsworker.finder import FOUND_ON_KEPT, FeedsFinder, _link_score
from newsworker.formats import format_scan
from newsworker.settings import Settings

ROOT = "https://site.test/"
HTML = {"Content-Type": "text/html; charset=utf-8"}
RSS = (
    b"<rss version='2.0'><channel><title>News</title><item><title>x</title></item></channel></rss>"
)

runner = CliRunner()


def page(*links, feeds=()):
    """An HTML page with ``(href, text)`` links and alternate RSS links in its head."""
    head = "".join(f"<link rel='alternate' type='application/rss+xml' href='{f}'>" for f in feeds)
    body = "".join(f"<a href='{href}'>{text}</a>" for href, text in links)
    return f"<html><head>{head}</head><body>{body}</body></html>".encode(), HTML


class SiteTransport:
    """Serves pages by URL; a missing URL fails like a 404, ``redirects`` map
    a requested URL to the page that answers it."""

    def __init__(self, pages, redirects=None):
        self.pages = pages
        self.redirects = redirects or {}
        self.calls = []

    def fetch(self, request, policy):
        self.calls.append(request.url)
        target = self.redirects.get(request.url, request.url)
        if target not in self.pages:
            raise FileNotFoundError(request.url)
        body, headers = self.pages[target]
        if isinstance(body, Exception):
            raise body
        return FetchResult(request.url, target, 200, headers, body)

    def fetched(self):
        return [url for url in self.calls if not url.endswith("/robots.txt")]


def crawl(transport, url=ROOT, **kwargs):
    return FeedsFinder(Settings(block_private_hosts=False), transport).find_feeds(
        url, crawl=True, **kwargs
    )


def by_url(result):
    return {item["url"]: item for item in result["items"]}


def test_feed_declared_on_a_section_page_is_found():
    transport = SiteTransport(
        {
            ROOT: page(("/about/", "About"), ("/news/", "News")),
            ROOT + "about/": page(),
            ROOT + "news/": page(feeds=["/news/rss.xml"]),
        }
    )
    result = crawl(transport)
    feed = by_url(result)[ROOT + "news/rss.xml"]
    assert feed["found_on"] == [ROOT + "news/"]
    assert feed["found_on_count"] == 1
    assert feed["verification"] == "unverified"
    assert result["crawl"] == {
        "pages_fetched": 3,
        "max_pages": 50,
        "max_depth": 2,
        "truncated": False,
        "skipped": {"robots": 0, "error": 0, "not_html": 0},
    }


def test_without_crawl_only_the_page_is_read_and_output_is_unchanged():
    transport = SiteTransport(
        {ROOT: page(("/news/", "News"), feeds=["/rss.xml"]), ROOT + "news/": page()}
    )
    result = FeedsFinder(Settings(block_private_hosts=False), transport).find_feeds(ROOT)
    assert transport.fetched() == [ROOT]
    assert "crawl" not in result
    assert "found_on" not in result["items"][0]


def test_news_sections_go_first_and_the_page_bound_stops_the_crawl():
    transport = SiteTransport(
        {
            ROOT: page(("/about/", "About us"), ("/contact/", "Contact"), ("/press/", "Press")),
            ROOT + "about/": page(),
            ROOT + "contact/": page(),
            ROOT + "press/": page(feeds=["/press.rss"]),
        }
    )
    result = crawl(transport, max_pages=2)
    assert transport.fetched() == [ROOT, ROOT + "press/"]
    assert result["crawl"]["truncated"] is True
    assert ROOT + "press.rss" in by_url(result)


def test_pagination_goes_last_and_hints_match_path_or_text():
    assert _link_score(ROOT + "news/page/2/", "next") == -1
    assert _link_score(ROOT + "news/?page=3", "3") == -1
    assert _link_score(ROOT + "novosti/", "") == 3
    assert _link_score(ROOT + "%D0%BD%D0%BE%D0%B2%D0%BE%D1%81%D1%82%D0%B8/", "") == 3
    assert _link_score(ROOT + "section/", "latest news") == 3
    assert _link_score(ROOT + "a/b/c/", "contact") == 0


def test_links_of_pages_at_the_depth_bound_are_not_followed():
    transport = SiteTransport(
        {
            ROOT: page(("/a/", "A")),
            ROOT + "a/": page(("/a/b/", "B")),
            ROOT + "a/b/": page(("/a/b/c/", "C"), feeds=["/b.rss"]),
            ROOT + "a/b/c/": page(feeds=["/c.rss"]),
        }
    )
    result = crawl(transport, max_depth=2)
    assert transport.fetched() == [ROOT, ROOT + "a/", ROOT + "a/b/"]
    assert ROOT + "b.rss" in by_url(result)
    assert ROOT + "c.rss" not in by_url(result)


def test_cycles_and_redirects_to_crawled_pages_are_read_once():
    transport = SiteTransport(
        {
            ROOT: page(("/news/", "News"), ("/old-news/", "Archive"), ("/#top", "Top")),
            ROOT + "news/": page(("/", "Home"), ("/news/#latest", "Latest"), feeds=["/rss"]),
        },
        redirects={ROOT + "old-news/": ROOT + "news/"},
    )
    result = crawl(transport)
    assert transport.fetched() == [ROOT, ROOT + "news/", ROOT + "old-news/"]
    assert by_url(result)[ROOT + "rss"]["found_on_count"] == 1
    assert result["crawl"]["pages_fetched"] == 3


def test_only_html_pages_of_the_same_site_are_visited():
    transport = SiteTransport(
        {
            ROOT: page(
                ("https://other.test/news/", "Other news"),
                ("https://blog.site.test/", "Blog"),
                ("https://www.site.test/press/", "Press"),
                ("/report.pdf", "Annual report"),
                ("/logo.PNG", "Logo"),
                ("/feed/", "Feed"),
                ("https://feeds.other.test/news.rss", "RSS"),
                ("mailto:editor@site.test", "Mail"),
                ("javascript:void(0)", "Menu"),
                ("http://[bad", "Broken"),
            ),
            "https://www.site.test/press/": page(),
        }
    )
    result = crawl(transport)
    assert transport.fetched() == [ROOT, "https://www.site.test/press/"]
    found = by_url(result)
    assert ROOT + "feed/" in found
    assert "https://feeds.other.test/news.rss" in found


def test_robots_disallowed_pages_are_skipped_and_counted():
    transport = SiteTransport(
        {
            ROOT + "robots.txt": (b"User-agent: *\nDisallow: /private/\n", {}),
            ROOT: page(("/private/news/", "Private news"), ("/news/", "News")),
            ROOT + "private/news/": page(feeds=["/private.rss"]),
            ROOT + "news/": page(),
        }
    )
    result = crawl(transport)
    assert ROOT + "private/news/" not in transport.fetched()
    assert result["crawl"]["skipped"]["robots"] == 1
    assert ROOT + "private.rss" not in by_url(result)


def test_robots_crawl_delay_paces_the_crawl():
    transport = SiteTransport(
        {
            ROOT + "robots.txt": (b"User-agent: *\nCrawl-delay: 2\n", {}),
            ROOT: page(("/news/", "News")),
            ROOT + "news/": page(),
        }
    )
    crawl(transport)
    assert HOSTS._hosts["site.test"].crawl_delay == 2


def test_failing_and_non_html_pages_are_counted_and_the_crawl_goes_on():
    transport = SiteTransport(
        {
            ROOT: page(("/broken/", "News 1"), ("/download/", "News 2"), ("/news/", "News")),
            ROOT + "broken/": (TimeoutError("slow"), HTML),
            ROOT + "download/": (b"%PDF-1.7", {"Content-Type": "application/pdf"}),
            ROOT + "news/": page(feeds=["/news.rss"]),
        }
    )
    result = crawl(transport)
    assert result["crawl"]["skipped"] == {"robots": 0, "error": 1, "not_html": 1}
    assert result["crawl"]["pages_fetched"] == 3
    assert ROOT + "news.rss" in by_url(result)


def test_failed_requests_count_against_the_page_bound():
    links = [(f"/news/{n}/", f"News {n}") for n in range(5)]
    transport = SiteTransport({ROOT: page(*links)})
    result = crawl(transport, max_pages=3)
    assert len(transport.fetched()) == 3
    assert result["crawl"]["skipped"]["error"] == 2
    assert result["crawl"]["truncated"] is True


def test_unreachable_start_page_is_an_error():
    result = crawl(SiteTransport({}))
    assert result["items"] == []
    assert result["error"].startswith("FileNotFoundError")
    assert "crawl" not in result


def test_site_wide_feed_counts_every_page_and_keeps_a_few():
    sections = [f"/news/{n}/" for n in range(7)]
    pages = {ROOT: page(*[(s, "News") for s in sections], feeds=["/rss"])}
    pages.update({ROOT + s.lstrip("/"): page(feeds=["/rss"]) for s in sections})
    result = crawl(SiteTransport(pages))
    feed = by_url(result)[ROOT + "rss"]
    assert feed["found_on_count"] == 8
    assert len(feed["found_on"]) == FOUND_ON_KEPT
    assert feed["found_on"][0] == ROOT


def test_start_url_that_is_a_feed_needs_no_crawl():
    transport = SiteTransport({ROOT + "rss": (RSS, {"Content-Type": "application/rss+xml"})})
    result = crawl(transport, url=ROOT + "rss")
    assert result["items"][0]["source"] == ["direct"]
    assert result["items"][0]["found_on"] == []
    assert result["crawl"]["pages_fetched"] == 1


def test_bounds_must_be_positive():
    with pytest.raises(ValueError):
        crawl(SiteTransport({ROOT: page()}), max_pages=0)
    with pytest.raises(ValueError):
        crawl(SiteTransport({ROOT: page()}), max_depth=0)


def test_listing_page_is_reported_from_the_fetched_body(news_list_html):
    transport = SiteTransport(
        {
            ROOT: page(("/news/", "News"), ("/about/", "About")),
            ROOT + "news/": (news_list_html, HTML),
            ROOT + "about/": page(),
        }
    )
    result = crawl(transport, extractrss=True)
    listing = by_url(result)[ROOT + "news/"]
    assert listing["feedtype"] == "html"
    assert listing["source"] == ["extraction"]
    assert listing["num_entries"] == 4
    assert listing["found_on"] == [ROOT + "news/"]
    assert 0 < listing["confidence"] <= 1
    assert ROOT not in by_url(result) and ROOT + "about/" not in by_url(result)
    assert transport.fetched().count(ROOT + "news/") == 1


def test_listing_extraction_uses_the_finder_settings(monkeypatch):
    seen = []

    def extracted(self, url, data=None):
        seen.append((self.settings.default_language, self.use_cache, data))
        return {"title": url, "items": []}, None

    monkeypatch.setattr("newsworker.service.FeedService.get_feed_with_diagnostics", extracted)
    body, headers = page()
    settings = Settings(block_private_hosts=False, default_language="de")
    FeedsFinder(settings, SiteTransport({ROOT: (body, headers)})).find_feeds(
        ROOT, crawl=True, extractrss=True
    )
    assert seen == [("de", False, body)]


def test_pages_with_fewer_than_three_dated_items_are_no_listing(monkeypatch):
    def extracted(self, url, data=None):
        dates = {ROOT: 2, ROOT + "news/": 3}.get(url, 0)
        items = [{"title": "dated", "pubdate": "2026-10-01"}] * dates + [{"title": "undated"}]
        return {"title": url, "items": items}, None

    monkeypatch.setattr("newsworker.service.FeedService.get_feed_with_diagnostics", extracted)
    transport = SiteTransport({ROOT: page(("/news/", "News")), ROOT + "news/": page()})
    result = crawl(transport, extractrss=True)
    assert [item["url"] for item in result["items"]] == [ROOT + "news/"]
    assert result["items"][0]["num_entries"] == 4


def test_csv_adds_found_on_only_for_a_crawl_and_opml_skips_listings():
    result = {
        "url": ROOT,
        "items": [
            {"title": "Feed", "url": ROOT + "rss", "feedtype": "rss", "found_on": [ROOT]},
            {"title": "News", "url": ROOT + "news/", "feedtype": "html", "found_on": []},
        ],
    }
    plain = next(csv.reader(io.StringIO(format_scan(result, fmt="csv"))))
    assert plain == ["title", "url", "feedtype", "num_entries", "language", "confidence"]
    rows = list(csv.DictReader(io.StringIO(format_scan({**result, "crawl": {}}, fmt="csv"))))
    assert [row["found_on"] for row in rows] == [ROOT, ""]
    opml = format_scan(result, fmt="opml")
    assert ROOT + "rss" in opml and ROOT + "news/" not in opml


def test_cli_passes_crawl_options(monkeypatch):
    captured = {}

    def find_feeds(self, url, **kwargs):
        captured.update(kwargs)
        return {"url": url, "items": [], "crawl": {"pages_fetched": 1}}

    monkeypatch.setattr("newsworker.core.FeedsFinder.find_feeds", find_feeds)
    result = runner.invoke(
        app, ["scan", ROOT, "--crawl", "--max-pages", "7", "--max-depth", "3", "--listings"]
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["crawl"] == {"pages_fetched": 1}
    assert captured["crawl"] is True and captured["extractrss"] is True
    assert (captured["max_pages"], captured["max_depth"]) == (7, 3)

    runner.invoke(app, ["scan", ROOT, "--crawl"])
    assert (captured["max_pages"], captured["max_depth"]) == (50, 2)
    runner.invoke(app, ["scan", ROOT])
    assert captured["crawl"] is False and captured["extractrss"] is False


def test_cli_crawl_writes_output_and_fails_on_empty(monkeypatch, tmp_path):
    transport = SiteTransport({ROOT: page(("/news/", "News")), ROOT + "news/": page()})
    monkeypatch.setattr("newsworker.finder.RequestsTransport", lambda: transport)
    output = tmp_path / "scan.json"
    result = runner.invoke(app, ["scan", ROOT, "--crawl", "-o", str(output)])
    assert result.exit_code == 0
    assert json.loads(output.read_text())["crawl"]["pages_fetched"] == 2
    empty = runner.invoke(app, ["scan", ROOT, "--crawl", "--fail-on-empty"])
    assert empty.exit_code == 3


@pytest.mark.parametrize(
    "args",
    [
        ["--max-pages", "5"],
        ["--max-depth", "1"],
        ["--crawl", "--max-pages", "0"],
        ["--crawl", "--max-depth", "-1"],
    ],
)
def test_cli_rejects_bounds_without_crawl_or_below_one(monkeypatch, args):
    monkeypatch.setattr(
        "newsworker.core.FeedsFinder.find_feeds",
        lambda self, url, **kwargs: pytest.fail("must not scan"),
    )
    assert runner.invoke(app, ["scan", ROOT, *args]).exit_code == 2
