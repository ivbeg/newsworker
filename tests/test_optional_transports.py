import asyncio
import os
import sys
import threading
import types
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from newsworker.async_fetch import _fetch_one, _ssl_context, aiohttp_available, fetch_urls_async
from newsworker.fetch import FetchPolicy, RedirectPolicyError, ResponseTooLarge
from newsworker.jsrender import (
    BrowserRenderError,
    BrowserRenderTimeout,
    BrowserUnavailable,
    PlaywrightExtractorPlugin,
    PlaywrightRenderer,
    RenderResult,
)


class AsyncContent:
    def __init__(self, chunks):
        self.chunks = chunks

    async def iter_chunked(self, size):
        for chunk in self.chunks:
            yield chunk


class AsyncResponse:
    def __init__(self, status=200, headers=None, chunks=None):
        self.status = status
        self.headers = headers or {}
        self.content = AsyncContent(chunks or [b"ok"])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        return None


class AsyncSession:
    def __init__(self, responses):
        self.responses = list(responses)

    def get(self, *args, **kwargs):
        return self.responses.pop(0)


@pytest.fixture
def fake_aiohttp(monkeypatch):
    module = types.SimpleNamespace(
        ClientTimeout=lambda total: total,
        ClientError=type("ClientError", (Exception,), {}),
    )
    monkeypatch.setitem(sys.modules, "aiohttp", module)
    return module


def test_async_adapter_success_redirect_304_and_bounds(fake_aiohttp):
    policy = FetchPolicy(block_private_hosts=False, max_bytes=4, redirect_limit=1)
    result = asyncio.run(
        _fetch_one(
            AsyncSession([AsyncResponse(chunks=[b"ab", b"cd"])]), "https://example.com", policy
        )
    )
    assert result.body == b"abcd"
    redirected = asyncio.run(
        _fetch_one(
            AsyncSession(
                [AsyncResponse(302, {"Location": "/next"}), AsyncResponse(chunks=[b"ok"])]
            ),
            "https://example.com",
            policy,
        )
    )
    assert redirected.redirect_chain == ("https://example.com/next",)
    unchanged = asyncio.run(
        _fetch_one(AsyncSession([AsyncResponse(304)]), "https://example.com", policy)
    )
    assert unchanged.not_modified
    with pytest.raises(ResponseTooLarge):
        asyncio.run(
            _fetch_one(
                AsyncSession([AsyncResponse(chunks=[b"12345"])]), "https://example.com", policy
            )
        )
    with pytest.raises(ResponseTooLarge):
        asyncio.run(
            _fetch_one(
                AsyncSession([AsyncResponse(headers={"Content-Length": "5"})]),
                "https://example.com",
                policy,
            )
        )
    with pytest.raises(RedirectPolicyError):
        asyncio.run(
            _fetch_one(
                AsyncSession([AsyncResponse(302, {"Location": "/next"})]),
                "https://example.com",
                FetchPolicy(block_private_hosts=False, redirect_limit=0),
            )
        )


def test_ssl_context_and_optional_availability():
    assert _ssl_context(True) is None
    assert _ssl_context(False).check_hostname is False
    assert isinstance(aiohttp_available(), bool)


def test_async_policy_headers_cookies_proxy_tls_and_concurrency(monkeypatch):
    captured = {}

    class Session(AsyncSession):
        def __init__(self, **kwargs):
            super().__init__([AsyncResponse(headers={"Content-Language": "fr"})])
            captured["session"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            captured["request"] = kwargs
            return super().get(*args, **kwargs)

    module = types.SimpleNamespace(
        ClientTimeout=lambda total: ("timeout", total),
        ClientError=type("ClientError", (Exception,), {}),
        TCPConnector=lambda **kwargs: ("connector", kwargs),
        ClientSession=Session,
    )
    monkeypatch.setitem(sys.modules, "aiohttp", module)
    cookies = {"session": "value"}
    policy = FetchPolicy(
        timeout=7,
        max_bytes=20,
        verify_tls=False,
        redirect_limit=2,
        block_private_hosts=False,
        proxy="http://proxy.example:8080",
        user_agent="agent",
        extra_headers={"X-Test": "yes"},
        cookies=cookies,
    )
    results = asyncio.run(
        fetch_urls_async(["https://example.com"], policy=policy, max_concurrency=1)
    )
    result = results["https://example.com"]
    assert result.content_language == "fr"
    assert captured["session"]["headers"] == {"X-Test": "yes", "User-Agent": "agent"}
    assert captured["session"]["cookies"] is cookies
    assert captured["request"]["proxy"] == "http://proxy.example:8080"
    assert captured["request"]["timeout"] == ("timeout", 7)
    assert captured["session"]["connector"][1]["ssl"].check_hostname is False


def test_browser_missing_and_plugin(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def missing_playwright(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_playwright)
    renderer = PlaywrightRenderer(FetchPolicy(block_private_hosts=False), timeout=1)
    with pytest.raises(BrowserUnavailable, match=r"newsworker\[browser\]"):
        renderer.render("https://example.com")

    class Renderer:
        def render(self, url):
            return RenderResult(
                b"<html><head><title>T</title></head><body></body></html>", url, 1.0
            )

    plugin = PlaywrightExtractorPlugin(Renderer())
    assert plugin.matches("https://example.com")
    feed = plugin.extract("https://example.com")
    assert feed["provenance"]["strategy"] == "browser"
    assert not PlaywrightExtractorPlugin(Renderer(), enabled=False).matches("https://example.com")


def _install_fake_playwright(monkeypatch, behavior="success"):
    state = {"aborted": 0, "continued": 0, "context_closed": 0, "browser_closed": 0}

    class Request:
        resource_type = "script"
        url = "http://127.0.0.1/private.js"
        redirected_from = None

        @staticmethod
        def is_navigation_request():
            return False

    class Route:
        request = Request()

        async def abort(self):
            state["aborted"] += 1

        async def continue_(self):
            state["continued"] += 1

    class Page:
        url = "https://93.184.216.34/page"

        async def route(self, pattern, handler):
            self.handler = handler

        async def goto(self, *args, **kwargs):
            await self.handler(Route())
            if behavior == "timeout":
                raise asyncio.TimeoutError()
            if behavior == "crash":
                raise RuntimeError("browser process exited")

        async def content(self):
            return "<html><body>rendered</body></html>"

    class Context:
        async def new_page(self):
            return Page()

        async def close(self):
            state["context_closed"] += 1

    class Browser:
        async def new_context(self, **kwargs):
            return Context()

        async def close(self):
            state["browser_closed"] += 1

    class Chromium:
        async def launch(self):
            return Browser()

    class Manager:
        async def __aenter__(self):
            return types.SimpleNamespace(chromium=Chromium())

        async def __aexit__(self, *args):
            return False

    async_api = types.ModuleType("playwright.async_api")
    async_api.async_playwright = Manager
    package = types.ModuleType("playwright")
    package.async_api = async_api
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.async_api", async_api)
    return state


def test_browser_blocks_subresources_and_cleans_up(monkeypatch):
    state = _install_fake_playwright(monkeypatch)
    renderer = PlaywrightRenderer(FetchPolicy(), timeout=1)
    result = renderer.render("https://93.184.216.34/page")
    assert result.body == b"<html><body>rendered</body></html>"
    assert state == {
        "aborted": 1,
        "continued": 0,
        "context_closed": 1,
        "browser_closed": 1,
    }


@pytest.mark.parametrize(
    ("behavior", "error_type"),
    [("timeout", BrowserRenderTimeout), ("crash", BrowserRenderError)],
)
def test_browser_classifies_failures_and_releases_resources(monkeypatch, behavior, error_type):
    state = _install_fake_playwright(monkeypatch, behavior)
    renderer = PlaywrightRenderer(FetchPolicy(), timeout=1)
    with pytest.raises(error_type):
        renderer.render("https://93.184.216.34/page")
    assert state["context_closed"] == 1
    assert state["browser_closed"] == 1
    assert renderer._semaphore.acquire(blocking=False)
    renderer._semaphore.release()


@pytest.mark.skipif(
    os.environ.get("NEWSWORKER_BROWSER_TESTS") != "1",
    reason="set NEWSWORKER_BROWSER_TESTS=1 after installing Playwright Chromium",
)
def test_browser_renders_deterministic_local_fixture():
    pytest.importorskip("playwright.async_api")
    fixture_dir = Path(__file__).parent / "fixtures"

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            return None

    handler = partial(QuietHandler, directory=str(fixture_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/js_listing.html"
        renderer = PlaywrightRenderer(
            FetchPolicy(block_private_hosts=False),
            timeout=10,
            max_bytes=128 * 1024,
            concurrency=1,
        )
        result = renderer.render(url)
        assert b"deterministic rendered headline" in result.body
        assert result.effective_url == url
        assert result.elapsed_ms > 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
