"""Per-host pacing: concurrency caps, Crawl-delay, Retry-After and robots caching."""

import concurrent.futures
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from newsworker.fetch import (
    HOSTS,
    FetchPolicy,
    FetchRequest,
    HostScheduler,
    RateLimited,
    RequestsTransport,
    retry_after_seconds,
)
from newsworker.tools import _RobotsCache


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_reserve_spaces_requests_by_interval_and_crawl_delay():
    clock = FakeClock()
    hosts = HostScheduler(clock=clock)
    assert hosts.reserve("a.example", interval=1.0) == 0
    assert hosts.reserve("a.example", interval=1.0) == pytest.approx(1.0)
    hosts.note_crawl_delay("b.example", 5)
    assert hosts.reserve("b.example") == 0
    assert hosts.reserve("b.example") == pytest.approx(5.0)
    assert hosts.reserve("c.example") == 0  # other hosts are independent


def test_retry_after_defers_and_fails_fast_beyond_the_limit():
    clock = FakeClock()
    hosts = HostScheduler(clock=clock)
    hosts.note_retry_after("a.example", 20)
    assert hosts.reserve("a.example", max_wait=30) == pytest.approx(20)
    hosts.note_retry_after("b.example", 10_000)
    with pytest.raises(RateLimited):
        hosts.reserve("b.example", max_wait=30)
    clock.now += 3600
    assert hosts.reserve("b.example", max_wait=30) == 0  # capped at MAX_RETRY_AFTER


def test_crawl_delay_is_capped():
    hosts = HostScheduler(clock=FakeClock())
    hosts.note_crawl_delay("a.example", 86_400)
    hosts.reserve("a.example")
    assert hosts.reserve("a.example", max_wait=120) == pytest.approx(60)


def test_scheduler_forgets_idle_hosts_beyond_its_bound(monkeypatch):
    clock = FakeClock()
    hosts = HostScheduler(clock=clock)
    monkeypatch.setattr(HostScheduler, "MAX_HOSTS", 3)
    for n in range(10):
        hosts.reserve(f"h{n}.example")
        clock.now += 1
    assert len(hosts._hosts) <= 3


def test_retry_after_header_forms():
    assert retry_after_seconds("120") == 120
    assert retry_after_seconds("Wed, 21 Oct 2015 07:28:00 GMT", now=1445412480 - 60) == 60
    assert retry_after_seconds("soon") is None
    assert retry_after_seconds(None) is None


class _Handler(BaseHTTPRequestHandler):
    active = 0
    peak = 0
    lock = threading.Lock()

    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path.startswith("/busy"):
            self.send_response(429)
            self.send_header("Retry-After", "120")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        with _Handler.lock:
            _Handler.active += 1
            _Handler.peak = max(_Handler.peak, _Handler.active)
        time.sleep(0.2)
        with _Handler.lock:
            _Handler.active -= 1
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    _Handler.active = _Handler.peak = 0
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def _policy(**values):
    return FetchPolicy(block_private_hosts=False, timeout=5, **values)


def test_concurrency_cap_applies_across_transports(server):
    policy = _policy(host_concurrency=1)

    def fetch(n):
        # A new transport per call, like separate batch workers.
        return RequestsTransport().fetch(FetchRequest(f"http://127.0.0.1:{server}/{n}"), policy)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch, range(4)))
    assert _Handler.peak == 1


def test_429_with_retry_after_pauses_the_host(server):
    policy = _policy(max_host_wait=5)
    transport = RequestsTransport()
    with pytest.raises(requests.HTTPError):
        transport.fetch(FetchRequest(f"http://127.0.0.1:{server}/busy"), policy)
    started = time.monotonic()
    with pytest.raises(RateLimited):
        transport.fetch(FetchRequest(f"http://127.0.0.1:{server}/next"), policy)
    assert time.monotonic() - started < 1


def test_delivery_requests_are_not_paced(server):
    HOSTS.note_retry_after("127.0.0.1", 600)
    result = RequestsTransport().fetch(
        FetchRequest(f"http://127.0.0.1:{server}/hook", operation="delivery"), _policy()
    )
    assert result.status == 200


def test_robots_crawl_delay_reaches_the_scheduler(monkeypatch):
    from newsworker.extractor import FeedExtractor

    extractor = FeedExtractor()

    class Result:
        body = b"User-agent: *\nCrawl-delay: 7\n"

    monkeypatch.setattr(extractor.transport, "fetch", lambda request, policy: Result())
    assert extractor._can_fetch_policy("https://slow.example/news", "newsworker/1.4")
    assert HOSTS._hosts["slow.example"].crawl_delay == 7


def test_robots_cache_expires_and_is_bounded():
    clock = FakeClock()
    cache = _RobotsCache(ttl=10, max_entries=2, clock=clock)
    cache["https://a"] = "rules-a"
    assert cache.get("https://a") == "rules-a"
    clock.now += 11
    assert cache.get("https://a", "missing") == "missing"
    for root in ("https://b", "https://c", "https://d"):
        cache[root] = root
    assert len(cache) == 2
    assert cache.get("https://b", "missing") == "missing"


def test_async_batch_honours_robots(tmp_path, monkeypatch):
    pytest.importorskip("aiohttp")
    from newsworker.service import FeedService
    from newsworker.settings import Settings

    service = FeedService(Settings(cache_dir=str(tmp_path)), use_cache=False)
    monkeypatch.setattr(service.extractor, "_can_fetch_policy", lambda url, agent: False)
    called = []
    monkeypatch.setattr(
        "newsworker.async_fetch.fetch_urls_concurrent",
        lambda urls, settings, max_workers, **kwargs: called.append(urls) or {},
    )
    results = service.get_feeds(["https://blocked.example/news"], use_async=True)
    assert results["https://blocked.example/news"]["error_type"] == "PermissionError"
    assert called == []
