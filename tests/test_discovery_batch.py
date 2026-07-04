"""Tests for sitemap discovery, OPML import and the batch command."""

import os

from typer.testing import CliRunner

from newsworker.core import app
from newsworker.finder import FeedsFinder
from newsworker.formats import read_opml


runner = CliRunner()

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/news</loc></url>
  <url><loc>https://example.com/feed.xml</loc></url>
  <url><loc>https://example.com/blog.rss</loc></url>
  <url><loc>https://example.com/about</loc></url>
</urlset>
"""

OPML = """<?xml version="1.0"?>
<opml version="2.0">
  <body>
    <outline text="Example" xmlUrl="https://example.com/feed.xml" htmlUrl="https://example.com/news"/>
    <outline text="No feed"/>
    <outline text="Other" title="Other" xmlUrl="https://other.example/atom.xml"/>
  </body>
</opml>
"""


class _Resp:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


def test_discover_sitemap_feeds(monkeypatch):
    finder = FeedsFinder()
    monkeypatch.setattr(
        "newsworker.finder.requests.get",
        lambda url, timeout=30: _Resp(SITEMAP.encode("utf-8")),
    )
    feeds = finder.discover_sitemap_feeds("https://example.com/")
    urls = {f["url"] for f in feeds}
    assert "https://example.com/feed.xml" in urls
    assert "https://example.com/blog.rss" in urls
    assert "https://example.com/about" not in urls


def test_discover_sitemap_missing_is_empty(monkeypatch):
    import requests

    def _boom(url, timeout=30):
        raise requests.exceptions.ConnectionError("nope")

    monkeypatch.setattr("newsworker.finder.requests.get", _boom)
    assert FeedsFinder().discover_sitemap_feeds("https://example.com/") == []


def test_read_opml_from_string():
    entries = read_opml(OPML)
    assert len(entries) == 2  # the outline without xmlUrl is skipped
    assert entries[0]["url"] == "https://example.com/feed.xml"
    assert entries[0]["html_url"] == "https://example.com/news"
    assert entries[1]["title"] == "Other"


def test_read_opml_from_file(tmp_path):
    path = tmp_path / "feeds.opml"
    path.write_text(OPML, encoding="utf-8")
    entries = read_opml(str(path))
    assert len(entries) == 2


def test_batch_command_writes_one_file_per_url(tmp_path, monkeypatch):
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text(
        "https://a.example/x\n# comment\nhttps://b.example/y\n", encoding="utf-8"
    )
    out_dir = tmp_path / "out"

    def fake_get_feeds(self, urls, max_workers=4, force_refresh=False):
        return {
            u: {"title": u, "link": u, "language": "en", "description": u, "items": []}
            for u in urls
        }

    monkeypatch.setattr("newsworker.service.FeedService.get_feeds", fake_get_feeds)
    # Avoid loading the real extractor/date patterns during FeedService init.
    monkeypatch.setattr(
        "newsworker.service.FeedService._build_extractor",
        lambda self: None,
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "batch",
            "--urls-file",
            str(urls_file),
            "--output-dir",
            str(out_dir),
            "--format",
            "json",
            "--no-cache",
        ],
    )
    assert result.exit_code == 0, result.stdout
    files = os.listdir(out_dir)
    assert len(files) == 2
    assert all(f.endswith(".json") for f in files)
