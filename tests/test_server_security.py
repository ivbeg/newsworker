import datetime as dt
from email.message import Message
from types import SimpleNamespace

from test_server_controls import request, start_server

from newsworker.formats import format_feed
from newsworker.server import FeedRequestHandler
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.tools import sanitize_feed_links


def _handler(client_ip, tokens=(), auth=None):
    handler = FeedRequestHandler.__new__(FeedRequestHandler)
    handler.client_address = (client_ip, 50000)
    headers = Message()
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    handler.headers = headers
    handler.server = SimpleNamespace(
        feed_service=SimpleNamespace(settings=Settings(api_tokens=list(tokens)))
    )
    return handler


def test_refresh_is_honoured_only_for_loopback_or_authenticated_clients():
    assert _handler("127.0.0.1")._may_force_refresh()
    assert _handler("::1")._may_force_refresh()
    assert not _handler("203.0.113.7")._may_force_refresh()
    assert _handler("203.0.113.7", tokens=["s3cret"], auth="s3cret")._may_force_refresh()
    assert not _handler("203.0.113.7", tokens=["s3cret"], auth="wrong")._may_force_refresh()


def test_loopback_refresh_reaches_the_service(tmp_path):
    settings = Settings(cache_dir=str(tmp_path))
    server = start_server(settings)
    seen = []
    original = server.feed_service.get_feed_with_diagnostics

    def recording(url, force_refresh=False):
        seen.append(force_refresh)
        return original(url, force_refresh=force_refresh)

    server.feed_service.get_feed_with_diagnostics = recording
    try:
        status, headers, _ = request(server, "GET", "/feed?url=https://example.org/&refresh=1")
        assert status == 200
        assert seen == [True]
        assert "Warning" not in headers
    finally:
        server.shutdown()
        server.server_close()


def test_unsafe_item_links_are_dropped():
    feed = {
        "items": [
            {
                "title": "x",
                "link": "javascript:alert(1)",
                "extra": {
                    "links": ["javascript:alert(1)", "https://a.example/1"],
                    "images": ["data:image/png;base64,AA", "https://a.example/i.png"],
                },
            },
            {"title": "y", "link": "https://a.example/2"},
        ]
    }
    sanitize_feed_links(feed, fallback_url="https://a.example/news")
    assert feed["items"][0]["link"] == "https://a.example/news"
    assert feed["items"][0]["extra"] == {
        "links": ["https://a.example/1"],
        "images": ["https://a.example/i.png"],
    }
    assert feed["items"][1]["link"] == "https://a.example/2"


def test_extraction_never_emits_javascript_links(tmp_path):
    html = b"""<html><body><ul>
    <li><span>16.10.2026</span> <a href="javascript:alert(1)">First headline about things</a></li>
    <li><span>15.10.2026</span> <a href="/two">Second headline about things</a></li>
    <li><span>14.10.2026</span> <a href="/three">Third headline about things</a></li>
    </ul></body></html>"""
    service = FeedService(Settings(cache_dir=str(tmp_path)), use_cache=False)
    feed = service.get_feed("https://news.example/list", data=html)
    links = [item["link"] for item in feed["items"]]
    assert links and all(link.startswith("https://") for link in links)


def test_html_preview_carries_a_restrictive_csp():
    feed = {
        "title": "t",
        "items": [
            {
                "title": "x",
                "link": "javascript:alert(1)",
                "pubdate": dt.datetime(2026, 10, 16, tzinfo=dt.timezone.utc),
            }
        ],
    }
    html = format_feed(feed, fmt="html")
    assert "Content-Security-Policy" in html and "default-src 'none'" in html
    assert "javascript:" not in html
