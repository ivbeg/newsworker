"""The aiohttp transport applies the same policy as the threaded one."""

import asyncio
import os
import threading
from http.cookiejar import Cookie, CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("aiohttp")

from newsworker import async_fetch  # noqa: E402
from newsworker.async_fetch import _guarded_resolver, fetch_urls_async  # noqa: E402
from newsworker.fetch import AddressPolicyError, FetchPolicy  # noqa: E402

PAGE = (
    "<html><body><ul>"
    + "".join(
        f'<li><a href="/n/{i}">Headline number {i} for the test</a> '
        f"<span>{day} October 2026</span></li>"
        for i, day in enumerate((15, 12, 9, 5), start=1)
    )
    + "</ul></body></html>"
).encode()


class Handler(BaseHTTPRequestHandler):
    seen: list = []

    def do_GET(self):  # noqa: N802
        Handler.seen.append((self.headers.get("Host"), self.path, dict(self.headers)))
        if self.path == "/hop":
            port = self.server.server_address[1]
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{port}/page")
            self.end_headers()
            return
        if self.headers.get("If-None-Match") == '"v1"':
            self.send_response(304)
            self.send_header("ETag", '"v1"')
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("ETag", '"v1"')
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    Handler.seen = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def _fetch(urls, policy, **kwargs):
    return asyncio.run(fetch_urls_async(urls, policy=policy, **kwargs))


def test_rebinding_to_a_private_address_is_refused_at_connection(server, monkeypatch):
    # The URL check saw a public address; the connection resolves to loopback.
    monkeypatch.setattr(async_fetch, "validate_destination", lambda url, policy: None)
    url = f"http://localhost:{server}/page"
    result = _fetch([url], FetchPolicy())[url]
    assert isinstance(result, AddressPolicyError)
    assert Handler.seen == []


def test_allow_listed_intranet_host_still_connects(server):
    url = f"http://localhost:{server}/page"
    policy = FetchPolicy(allow_private_hosts=True, allowed_hosts=("localhost",))
    assert _fetch([url], policy)[url].status == 200


def test_proxy_host_is_not_treated_as_a_destination():
    async def resolve(policy):
        resolver = _guarded_resolver(policy)
        try:
            return await resolver.resolve("localhost", 3128)
        finally:
            await resolver.close()

    assert asyncio.run(resolve(FetchPolicy(proxy="http://localhost:3128")))
    with pytest.raises(AddressPolicyError):
        asyncio.run(resolve(FetchPolicy(proxy="http://proxy.example:3128")))


def test_credentials_are_dropped_on_cross_origin_redirect(server):
    url = f"http://localhost:{server}/hop"
    policy = FetchPolicy(
        block_private_hosts=False,
        user_agent="agent/1",
        extra_headers={"Authorization": "Bearer secret", "X-Site-Key": "k"},
    )
    result = _fetch([url], policy)[url]
    assert result.effective_url == f"http://127.0.0.1:{server}/page"
    (_, _, first), (_, _, second) = Handler.seen
    assert first["Authorization"] == "Bearer secret" and first["X-Site-Key"] == "k"
    assert "Authorization" not in second and "X-Site-Key" not in second
    assert second["User-Agent"] == "agent/1"


def _cookie(domain, name, value):
    return Cookie(
        0, name, value, None, False, domain, True, domain.startswith("."), "/", True,
        False, None, False, None, None, {},
    )  # fmt: skip


def test_cookie_file_cookies_stay_on_their_domain(server):
    jar = CookieJar()
    jar.set_cookie(_cookie("localhost", "session", "abc"))
    jar.set_cookie(_cookie("other.example", "foreign", "x"))
    policy = FetchPolicy(block_private_hosts=False, cookies=jar)
    url = f"http://localhost:{server}/hop"
    _fetch([url], policy)
    (_, _, first), (_, _, second) = Handler.seen
    assert first.get("Cookie") == "session=abc"
    assert "Cookie" not in second


def test_async_batch_uses_the_content_cache_and_revalidates(server, tmp_path):
    from newsworker.service import FeedService
    from newsworker.settings import Settings

    settings = Settings(
        cache_dir=str(tmp_path),
        block_private_hosts=False,
        respect_robots=False,
        use_async=True,
    )
    service = FeedService(settings, plugins=[], bridges=[])
    url = f"http://127.0.0.1:{server}/page"

    runtime: dict = {}
    first = service.get_feeds([url], runtime=runtime)
    assert len(first[url]["items"]) == 4
    assert runtime[url]["cache_state"] == "miss"

    runtime = {}
    service.get_feeds([url], runtime=runtime)
    assert runtime[url]["cache_state"] == "hit"
    assert len(Handler.seen) == 1

    os.utime(service.content_cache._path(url), (0, 0))
    runtime = {}
    again = service.get_feeds([url], runtime=runtime)
    assert runtime[url]["cache_state"] == "revalidated"
    assert Handler.seen[-1][2]["If-None-Match"] == '"v1"'
    assert len(again[url]["items"]) == 4

    runtime = {}
    service.get_feeds([url], force_refresh=True, runtime=runtime)
    assert runtime[url]["cache_state"] == "changed"
    assert "If-None-Match" not in Handler.seen[-1][2]
