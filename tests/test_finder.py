import json

import pytest
from lxml import etree
from lxml.html import fromstring

from newsworker.fetch import FetchResult
from newsworker.finder import FeedCandidate, FeedsFinder, _merge_candidates, get_url_data
from newsworker.settings import Settings


def _parse(html_bytes):
    parser = etree.HTMLParser(remove_blank_text=True)
    return fromstring(html_bytes, parser=parser)


def test_collect_feeds_finds_autodiscovery_links(news_list_html):
    root = _parse(news_list_html)
    finder = FeedsFinder()
    feeds = finder.collect_feeds(root, "https://example.com/")
    urls = {f["url"] for f in feeds}
    assert "https://example.com/feed.xml" in urls
    assert "https://example.com/atom.xml" in urls


def test_collect_feeds_records_feedtypes(news_list_html):
    root = _parse(news_list_html)
    finder = FeedsFinder()
    feeds = finder.collect_feeds(root, "https://example.com/")
    by_url = {f["url"]: f for f in feeds}
    assert by_url["https://example.com/feed.xml"]["feedtype"] == "rss"
    assert by_url["https://example.com/atom.xml"]["feedtype"] == "atom"


def test_collect_feeds_deduplicates(news_list_html):
    root = _parse(news_list_html)
    finder = FeedsFinder()
    feeds = finder.collect_feeds(root, "https://example.com/")
    urls = [f["url"] for f in feeds]
    assert len(urls) == len(set(urls))


def test_candidate_optional_fields_and_rich_collection():
    candidate = FeedCandidate(
        "https://example.com/feed",
        verification_error="bad",
        num_entries=2,
        language="fr",
        hubs=["https://hub.example"],
        self_url="https://example.com/feed",
        entries=[{"id": "1"}],
    ).to_dict()
    assert candidate["language"] == "fr" and candidate["entries"]
    html = b"""<html><head>
      <link rel='hub' href='https://hub.example'>
      <link rel='self' href='/page'>
      <link rel='alternate' type='application/rss+xml' href='/same'>
    </head><body>
      <a href='/same'>RSS feed</a><a href='/atom'>feed</a>
      <a href='mailto:x'>RSS</a><a href='/icon'><img src='rss.png' alt='RSS'></a>
    </body></html>"""
    feeds = FeedsFinder().collect_feeds(_parse(html), "https://example.com/")
    by_url = {feed["url"]: feed for feed in feeds}
    assert by_url["https://example.com/same"]["source"] == [
        "autodiscovery",
        "link-heuristic",
    ]
    assert by_url["https://example.com/same"]["hubs"] == ["https://hub.example"]
    assert by_url["https://example.com/icon"]["source"] == ["feed-icon"]


def test_parse_json_and_atom_feed_variants():
    finder = FeedsFinder(Settings(block_private_hosts=False))
    payload = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "JSON",
        "language": "fr",
        "items": [{"id": "1"}],
        "hubs": [{"type": "WebSub", "url": "https://hub.example"}, "bad"],
    }
    fetched = FetchResult(
        "https://example.com/feed.json",
        "https://example.com/feed.json",
        200,
        {"Content-Type": "application/feed+json"},
        json.dumps(payload).encode(),
    )
    parsed = finder._parse_feed(fetched, "jsonfeed", True)
    assert parsed["language"] == "fr" and parsed["entries"] == [{"id": "1"}]
    assert parsed["hubs"] == ["https://hub.example"]
    invalid = FetchResult("u", "u", 200, {}, b"{}")
    with pytest.raises(ValueError):
        finder._parse_feed(invalid, "jsonfeed", False)

    atom = b"""<feed xmlns='http://www.w3.org/2005/Atom' xml:lang='de'><title>A</title>
    <link rel='hub' href='https://hub.example'/><link rel='self' href='https://example.com/a'/>
    <entry><id>1</id><title>One</title></entry></feed>"""
    parsed = finder._parse_feed(FetchResult("u", "u", 200, {}, atom), "atom", True)
    assert parsed["feedtype"] == "atom" and len(parsed["entries"]) == 1
    assert parsed["self_url"] == "https://example.com/a"
    with pytest.raises(ValueError):
        finder._parse_feed(FetchResult("u", "u", 200, {}, b"not a feed"), "rss", False)


class Transport:
    def __init__(self, values):
        self.values = list(values)

    def fetch(self, request, policy):
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_find_direct_failure_malformed_extractrss_and_deep(monkeypatch):
    direct = FetchResult(
        "https://example.com/feed.json",
        "https://example.com/feed.json",
        200,
        {"Content-Type": "application/feed+json"},
        json.dumps(
            {
                "version": "https://jsonfeed.org/version/1.1",
                "title": "J",
                "items": [],
            }
        ).encode(),
    )
    result = FeedsFinder(Settings(block_private_hosts=False), Transport([direct])).find_feeds(
        "https://example.com/feed.json"
    )
    assert result["items"][0]["source"] == ["direct"]
    failed = FeedsFinder(
        Settings(block_private_hosts=False), Transport([RuntimeError("no")])
    ).find_feeds("https://example.com")
    assert failed["items"] == []
    malformed = FetchResult("u", "https://example.com", 200, {}, b"\x00")
    assert (
        FeedsFinder(Settings(block_private_hosts=False), Transport([malformed])).find_feeds(
            "https://example.com"
        )["items"]
        == []
    )

    page = FetchResult(
        "u",
        "https://example.com",
        200,
        {"Content-Type": "text/html"},
        b"<html><body><main></main></body></html>",
    )
    monkeypatch.setattr(
        "newsworker.extractor.FeedExtractor.get_feed",
        lambda self, url, data=None: ({"title": "HTML", "items": [{"title": "x"}]}, {}),
    )
    finder = FeedsFinder(Settings(block_private_hosts=False), Transport([page]))
    assert (
        finder.find_feeds("https://example.com", extractrss=True)["items"][0]["feedtype"] == "html"
    )

    monkeypatch.setattr(
        FeedsFinder,
        "find_feeds",
        lambda self, url, **kwargs: {"url": url, "kwargs": kwargs},
    )
    assert FeedsFinder().find_feeds_deep("https://example.com")["kwargs"]["noverify"] is False


def test_merge_candidates_and_get_url_data(monkeypatch):
    merged = _merge_candidates(
        [
            {
                "url": "HTTPS://EXAMPLE.COM/feed#one",
                "feedtype": "undefined",
                "source": ["one"],
                "confidence": 0.2,
            },
            {
                "url": "https://example.com/feed",
                "feedtype": "rss",
                "source": ["two", "one"],
                "confidence": 0.9,
            },
        ]
    )
    assert merged[0]["feedtype"] == "rss"
    assert merged[0]["source"] == ["one", "two"]
    assert merged[0]["confidence"] == 0.9

    fetched = FetchResult("u", "https://example.com/final", 200, {}, b"<html></html>")
    monkeypatch.setattr(FeedsFinder, "_fetch", lambda self, url: fetched)
    root, url = get_url_data("https://example.com")
    assert root.tag == "html" and url.endswith("/final")
    monkeypatch.setattr(
        FeedsFinder, "_fetch", lambda self, url: (_ for _ in ()).throw(RuntimeError("bad"))
    )
    assert get_url_data("https://example.com") == (None, None)
