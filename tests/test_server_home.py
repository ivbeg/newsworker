"""The ``/`` page: paste a URL, preview the items, copy the feed link."""

import datetime as dt
import http.client
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import quote

from newsworker.server import INDEX_TEXT, FeedRequestHandler, TokenBucketLimiter
from newsworker.settings import Settings

BROWSER = {"Accept": "text/html,application/xhtml+xml"}
SOURCE = "https://news.example.org/list"


class PreviewService:
    def __init__(self, settings):
        self.settings = settings
        self.calls = 0

    def get_feed_with_diagnostics(self, url, force_refresh=False):
        self.calls += 1
        items = [
            {
                "title": "<script>alert(1)</script> Budget passed",
                "link": "https://news.example.org/1",
                "pubdate": dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc),
            },
            {"title": "No link here", "link": "javascript:alert(1)", "pubdate": None},
        ]
        return {"title": "Example News", "link": url, "items": items}, None


def start(settings):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FeedRequestHandler)
    server.feed_service = PreviewService(settings)
    server.rate_limiter = TokenBucketLimiter(0, 20)
    server.build_semaphore = threading.BoundedSemaphore(2)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _get(server, path, headers=BROWSER):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
    connection.request("GET", path, headers=headers)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read().decode("utf-8")
    connection.close()
    return result


def test_plain_clients_still_get_the_text_index(tmp_path):
    server = start(Settings(cache_dir=str(tmp_path)))
    try:
        status, _, body = _get(server, "/", headers={})
        assert status == 200 and body == INDEX_TEXT
    finally:
        server.shutdown()
        server.server_close()


def test_form_previews_items_and_offers_the_feed_link(tmp_path):
    server = start(Settings(cache_dir=str(tmp_path), port=8787))
    try:
        status, headers, body = _get(server, "/")
        assert status == 200 and '<form method="get" action="/">' in body
        assert "form-action 'self'" in headers["Content-Security-Policy"]
        assert "script-src" not in headers["Content-Security-Policy"]

        status, headers, body = _get(server, f"/?url={quote(SOURCE)}&format=rss")
        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        assert "/feed?url=https%3A%2F%2Fnews.example.org%2Flist&amp;format=rss" in body
        assert "&lt;script&gt;alert(1)&lt;/script&gt; Budget passed" in body
        assert "<script>" not in body
        assert 'href="https://news.example.org/1"' in body
        assert "javascript:" not in body
        assert "2026-10-15" in body
    finally:
        server.shutdown()
        server.server_close()


def test_rejected_url_is_reported_on_the_page(tmp_path):
    server = start(Settings(cache_dir=str(tmp_path)))
    try:
        status, _, body = _get(server, "/?url=file%3A%2F%2F%2Fetc%2Fpasswd")
        assert status == 400 and "Rejected URL" in body
        assert server.feed_service.calls == 0
    finally:
        server.shutdown()
        server.server_close()


def test_protected_servers_do_not_mint_links_for_anonymous_clients(tmp_path):
    server = start(Settings(cache_dir=str(tmp_path), api_tokens=["t" * 20]))
    try:
        status, _, body = _get(server, f"/?url={quote(SOURCE)}")
        assert status == 200 and "This server is protected" in body
        assert server.feed_service.calls == 0
        headers = dict(BROWSER, Authorization="Bearer " + "t" * 20)
        status, _, body = _get(server, f"/?url={quote(SOURCE)}", headers=headers)
        assert "Budget passed" in body
    finally:
        server.shutdown()
        server.server_close()


def test_signing_key_lets_only_the_local_operator_mint_signed_links(tmp_path):
    server = start(Settings(cache_dir=str(tmp_path), feed_signing_key="k" * 32))
    try:
        # The test client connects from loopback, so it acts as the operator.
        status, _, body = _get(server, f"/?url={quote(SOURCE)}&format=atom")
        assert status == 200 and "&amp;sig=" in body
    finally:
        server.shutdown()
        server.server_close()
    remote = FeedRequestHandler._home_allowed
    probe = type(
        "Probe",
        (),
        {
            "client_address": ("203.0.113.9", 1),
            "settings": Settings(cache_dir=str(tmp_path), feed_signing_key="k" * 32),
            "_tokens": FeedRequestHandler._tokens,
            "_signing_key": FeedRequestHandler._signing_key,
            "_is_loopback": FeedRequestHandler._is_loopback,
        },
    )()
    assert remote(probe) is False
