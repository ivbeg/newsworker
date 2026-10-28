"""Feed discovery (scan, MCP find_feeds) honours robots.txt like extraction."""

from typer.testing import CliRunner

from newsworker.core import app
from newsworker.fetch import HOSTS, FetchResult
from newsworker.finder import FeedsFinder
from newsworker.mcp_server import find_feeds
from newsworker.settings import Settings
from newsworker.tools import ROBOTS_MAX_BYTES, robots_allows

ROBOTS = b"User-agent: *\nDisallow: /private/\nCrawl-delay: 2\n"
RSS = b"<rss version='2.0'><channel><title>OK</title><item><title>x</title></item></channel></rss>"
PAGE = b"""<html><head>
  <link rel='alternate' type='application/rss+xml' href='/private/feed.xml'>
  <link rel='alternate' type='application/rss+xml' href='/feed.xml'>
</head></html>"""
INDEX = b"""<sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
  <sitemap><loc>https://example.com/private/sitemap.xml</loc></sitemap>
  <sitemap><loc>https://example.com/public/sitemap.xml</loc></sitemap></sitemapindex>"""
PRIVATE_SITEMAP = b"""<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
  <url><loc>https://example.com/private.rss</loc></url></urlset>"""
PUBLIC_SITEMAP = b"""<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
  <url><loc>https://example.com/public.rss</loc></url></urlset>"""


class MapTransport:
    """Serves bodies by URL; a missing URL fails like a 404."""

    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def fetch(self, request, policy):
        self.calls.append((request.url, policy.max_bytes))
        if request.url not in self.mapping:
            raise FileNotFoundError(request.url)
        body, headers = self.mapping[request.url]
        return FetchResult(request.url, request.url, 200, headers, body)

    def urls(self):
        return [url for url, _ in self.calls]


def _site(**extra):
    return {
        "https://example.com/robots.txt": (ROBOTS, {}),
        "https://example.com/": (PAGE, {"Content-Type": "text/html"}),
        "https://example.com/private/page": (PAGE, {"Content-Type": "text/html"}),
        "https://example.com/feed.xml": (RSS, {"Content-Type": "application/rss+xml"}),
        "https://example.com/private/feed.xml": (RSS, {"Content-Type": "application/rss+xml"}),
        **extra,
    }


def _finder(transport, **settings):
    return FeedsFinder(Settings(block_private_hosts=False, **settings), transport)


def test_disallowed_start_page_is_an_error_and_not_fetched():
    transport = MapTransport(_site())
    result = _finder(transport).find_feeds("https://example.com/private/page")
    assert result["url"] == "https://example.com/private/page"
    assert result["items"] == []
    assert result["error"] == (
        "PermissionError: robots.txt disallows fetching https://example.com/private/page"
    )
    assert transport.urls() == ["https://example.com/robots.txt"]


def test_robots_fetch_is_capped_and_crawl_delay_reaches_the_scheduler():
    transport = MapTransport(_site())
    _finder(transport).find_feeds("https://example.com/")
    assert transport.calls[0] == ("https://example.com/robots.txt", ROBOTS_MAX_BYTES)
    assert HOSTS._hosts["example.com"].crawl_delay == 2


def test_disallowed_candidate_is_invalid_without_a_fetch():
    transport = MapTransport(_site())
    result = _finder(transport).find_feeds("https://example.com/", noverify=False)
    items = {item["url"]: item for item in result["items"]}
    blocked = items["https://example.com/private/feed.xml"]
    assert blocked["verification"] == "invalid"
    assert blocked["verification_error"] == (
        "PermissionError: robots.txt disallows fetching https://example.com/private/feed.xml"
    )
    assert items["https://example.com/feed.xml"]["verification"] == "valid"
    assert "https://example.com/private/feed.xml" not in transport.urls()
    assert transport.urls().count("https://example.com/robots.txt") == 1


def test_disallowed_sitemap_document_is_skipped():
    transport = MapTransport(
        _site(
            **{
                "https://example.com/sitemap.xml": (INDEX, {}),
                "https://example.com/private/sitemap.xml": (PRIVATE_SITEMAP, {}),
                "https://example.com/public/sitemap.xml": (PUBLIC_SITEMAP, {}),
            }
        )
    )
    urls = {
        item["url"]
        for item in _finder(transport).find_feeds("https://example.com/", include_sitemap=True)[
            "items"
        ]
    }
    assert "https://example.com/public.rss" in urls
    assert "https://example.com/private.rss" not in urls
    assert "https://example.com/private/sitemap.xml" not in transport.urls()


def test_missing_robots_allows_everything():
    site = _site()
    del site["https://example.com/robots.txt"]
    transport = MapTransport(site)
    result = _finder(transport).find_feeds("https://example.com/private/page", noverify=False)
    assert "error" not in result
    assert {item["verification"] for item in result["items"]} == {"valid"}


def test_respect_robots_off_never_reads_robots():
    transport = MapTransport(_site())
    result = _finder(transport, respect_robots=False).find_feeds(
        "https://example.com/private/page", noverify=False
    )
    assert "error" not in result
    assert {item["verification"] for item in result["items"]} == {"valid"}
    assert "https://example.com/robots.txt" not in transport.urls()
    assert "example.com" not in HOSTS._hosts


def test_scan_exits_1_and_mcp_reports_error_on_disallowed_page(tmp_path, monkeypatch):
    transport = MapTransport(_site())
    monkeypatch.setattr("newsworker.finder.RequestsTransport", lambda: transport)
    monkeypatch.delenv("NEWSWORKER_RESPECT_ROBOTS", raising=False)
    config = tmp_path / "config.yaml"
    config.write_text("block_private_hosts: false\n", encoding="utf-8")
    scan = CliRunner().invoke(
        app, ["scan", "https://example.com/private/page", "--config", str(config)]
    )
    assert scan.exit_code == 1
    assert "https://example.com/private/page" not in transport.urls()

    result = find_feeds(Settings(block_private_hosts=False), "https://example.com/private/page")
    assert result["feeds"] == []
    assert result["error"].startswith("PermissionError: robots.txt disallows")


def test_scan_ignore_robots_scans_disallowed_page(tmp_path, monkeypatch):
    transport = MapTransport(_site())
    monkeypatch.setattr("newsworker.finder.RequestsTransport", lambda: transport)
    monkeypatch.delenv("NEWSWORKER_RESPECT_ROBOTS", raising=False)
    config = tmp_path / "config.yaml"
    config.write_text("block_private_hosts: false\n", encoding="utf-8")
    scan = CliRunner().invoke(
        app,
        ["scan", "https://example.com/private/page", "--ignore-robots", "--config", str(config)],
    )
    assert scan.exit_code == 0, scan.output
    assert "https://example.com/private/feed.xml" in scan.stdout
    assert "https://example.com/private/page" in transport.urls()
    assert "https://example.com/robots.txt" not in transport.urls()


def test_robots_allows_uses_request_rate_and_is_lenient():
    rules = b"User-agent: *\nRequest-rate: 1/5\nDisallow: /x\n"
    assert not robots_allows("https://rate.example/x", lambda url: rules, "newsworker")
    assert HOSTS._hosts["rate.example"].crawl_delay == 5
    assert robots_allows("https://rate.example/y", lambda url: rules)

    def unreadable(url):
        raise TimeoutError(url)

    assert robots_allows("https://down.example/x", unreadable)
    assert robots_allows("mailto:someone@example.com", unreadable)
