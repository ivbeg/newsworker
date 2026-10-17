import datetime as dt
import json

from newsworker.native import looks_like_feed, parse_native_feed
from newsworker.service import FeedService
from newsworker.settings import Settings

UTC = dt.timezone.utc
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>R</title>
<link>https://r.example/</link><language>ru-RU</language>
<item><title>Rates decision</title><link>/news/1</link><guid>g-1</guid>
<pubDate>Thu, 15 Oct 2026 10:00:00 +0300</pubDate><category>Economy</category>
<author>press@r.example (Press)</author><description>Summary</description></item>
<item><title>Second</title><link>javascript:alert(1)</link><guid>g-2</guid></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom">
<title>A</title><link href="https://a.example/"/><id>urn:a</id><updated>2026-10-15T08:00:00Z</updated>
<entry><title>Atom entry</title><link href="https://a.example/e1"/><id>urn:a:1</id>
<updated>2026-10-15T08:00:00Z</updated><content type="html">&lt;p&gt;Body&lt;/p&gt;</content></entry>
</feed>"""
JSON_FEED = json.dumps(
    {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "J",
        "home_page_url": "https://j.example/",
        "language": "de",
        "items": [
            {
                "id": "j-1",
                "url": "https://j.example/1",
                "title": "Eins",
                "date_published": "2026-10-15T10:00:00+02:00",
                "content_html": "<p>x</p>",
                "authors": [{"name": "Ann"}],
                "tags": ["a"],
            }
        ],
    }
).encode()


def test_detection():
    assert looks_like_feed(RSS) and looks_like_feed(ATOM) and looks_like_feed(JSON_FEED)
    assert not looks_like_feed(b"<!DOCTYPE html><html><body>news</body></html>")
    assert not looks_like_feed(b'{"items": []}')
    assert not looks_like_feed(b"<?xml version='1.0'?><svg/>", "image/svg+xml")


def test_rss_entries_keep_publisher_metadata():
    feed = parse_native_feed(RSS, "https://r.example/rss")
    first = feed["items"][0]
    assert feed["native_format"] == "rss20" and feed["language"] == "ru"
    assert first["link"] == "https://r.example/news/1"
    assert first["pubdate"] == dt.datetime(2026, 10, 15, 7, 0, tzinfo=UTC)
    assert first["native_id"] == "g-1" and first["categories"] == ["Economy"]


def test_atom_content_kind_and_json_feed():
    atom = parse_native_feed(ATOM, "https://a.example/atom")["items"][0]
    assert atom["content_kind"] == "html" and "<p>Body</p>" in atom["content"]
    item = parse_native_feed(JSON_FEED, "https://j.example/feed.json")["items"][0]
    assert item["pubdate"] == dt.datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
    assert item["author"] == "Ann" and item["content_kind"] == "html"


def test_service_reads_native_feeds_and_keeps_entry_ids(tmp_path):
    service = FeedService(Settings(cache_dir=str(tmp_path)), use_cache=False)
    feed, diagnostics = service.get_feed_with_diagnostics("https://r.example/rss", data=RSS)
    assert diagnostics.chosen_strategy == "native_feed"
    assert feed["language"] == "ru"
    assert [item["native_id"] for item in feed["items"]] == ["g-1", "g-2"]
    # Unsafe links are dropped like for HTML pages.
    assert feed["items"][1]["link"] == "https://r.example/rss"
    again = service.get_feed("https://r.example/rss", data=RSS.replace(b"Summary", b"Edited"))
    assert again["items"][0]["unique_id"] == feed["items"][0]["unique_id"]


def test_native_feeds_can_be_disabled(tmp_path):
    service = FeedService(Settings(cache_dir=str(tmp_path), native_feeds=False), use_cache=False)
    _feed, diagnostics = service.get_feed_with_diagnostics("https://r.example/rss", data=RSS)
    assert diagnostics.chosen_strategy != "native_feed"


def test_batch_reads_opml_feeds_natively_unless_pages_requested(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    import newsworker.core as core

    opml = tmp_path / "subs.opml"
    opml.write_text(
        '<opml version="2.0"><body><outline text="R" xmlUrl="https://r.example/rss" '
        'htmlUrl="https://r.example/news"/></body></opml>'
    )
    config = tmp_path / "config.yaml"
    config.write_text(f"cache_dir: {tmp_path / 'cache'}\n")
    seen = []

    class Service:
        def __init__(self, settings, use_cache=True):
            pass

        def get_feeds(self, urls, max_workers=4, runtime=None):
            seen.append(list(urls))
            return {url: {"title": "T", "items": []} for url in urls}

    monkeypatch.setattr(core, "FeedService", Service)
    args = ["batch", "--from-opml", str(opml), "-d", str(tmp_path / "out"), "-c", str(config)]
    assert CliRunner().invoke(core.app, args).exit_code == 0
    assert CliRunner().invoke(core.app, args + ["--opml-pages"]).exit_code == 0
    assert seen == [["https://r.example/rss"], ["https://r.example/news"]]
