"""Feed discovery: JSON Feed, WebSub and sitemap indexes."""

import json

from newsworker.fetch import (
    FetchResult,
)
from newsworker.finder import FeedsFinder
from newsworker.settings import Settings


class MapTransport:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def fetch(self, request, policy):
        self.calls.append(request.url)
        value = self.mapping[request.url]
        if isinstance(value, Exception):
            raise value
        body, headers = value
        return FetchResult(request.url, request.url, 200, headers, body)


def test_modern_discovery_jsonfeed_websub_and_sitemap_indexes():
    html = b"""<html><head>
      <link rel='alternate stylesheet' type='application/feed+json' href='/feed.json' title='JSON'>
      <link rel='alternate' type='application/atom+xml' href='/atom.xml'>
    </head></html>"""
    json_feed = json.dumps(
        {
            "version": "https://jsonfeed.org/version/1.1",
            "title": "JSON News",
            "items": [{"id": "1", "content_text": "hello"}],
            "hubs": [{"type": "WebSub", "url": "https://hub.example"}],
        }
    ).encode()
    atom = b"""<feed xmlns='http://www.w3.org/2005/Atom'><title>A</title>
      <link rel='self' href='https://example.com/atom.xml'/>
      <link rel='hub' href='https://hub.example'/><entry><id>1</id><title>x</title></entry></feed>"""
    index = b"""<sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
      <sitemap><loc>https://example.com/nested.xml</loc></sitemap></sitemapindex>"""
    nested = b"""<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
      <url><loc>https://example.com/feed.json</loc></url></urlset>"""
    transport = MapTransport(
        {
            "https://example.com/": (html, {"Content-Type": "text/html"}),
            "https://example.com/feed.json": (json_feed, {"Content-Type": "application/feed+json"}),
            "https://example.com/atom.xml": (atom, {"Content-Type": "application/atom+xml"}),
            "https://example.com/sitemap.xml": (index, {}),
            "https://example.com/nested.xml": (nested, {}),
        }
    )
    finder = FeedsFinder(Settings(block_private_hosts=False), transport=transport)
    results = finder.find_feeds("https://example.com/", noverify=False, include_sitemap=True)
    by_type = {item["feedtype"]: item for item in results["items"]}
    assert by_type["jsonfeed"]["verification"] == "valid"
    assert by_type["atom"]["hubs"] == ["https://hub.example"]
    assert "https://example.com/nested.xml" in transport.calls


def test_discovery_invalid_candidate_does_not_abort_others():
    html = b"<html><head><link rel='alternate' type='application/feed+json' href='/bad.json'><link rel='alternate' type='application/rss+xml' href='/ok.xml'></head></html>"
    rss = b"<rss version='2.0'><channel><title>OK</title><item><title>x</title></item></channel></rss>"
    transport = MapTransport(
        {
            "https://example.com/": (html, {"Content-Type": "text/html"}),
            "https://example.com/bad.json": (b"{}", {"Content-Type": "application/feed+json"}),
            "https://example.com/ok.xml": (rss, {"Content-Type": "application/rss+xml"}),
        }
    )
    results = FeedsFinder(Settings(block_private_hosts=False), transport).find_feeds(
        "https://example.com/", noverify=False
    )
    states = {item["url"]: item["verification"] for item in results["items"]}
    assert states["https://example.com/bad.json"] == "invalid"
    assert states["https://example.com/ok.xml"] == "valid"
