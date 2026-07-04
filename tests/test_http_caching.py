"""Tests for conditional caching, upstream revalidation and cache write safety."""

import http.client
import os
import threading
import time
from http.server import ThreadingHTTPServer

from newsworker.cache import ContentCache
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker import server as server_mod


# ---------------------------------------------------------------------------
# Cache write safety + metadata
# ---------------------------------------------------------------------------


def test_content_cache_concurrent_writes_never_corrupt(tmp_path):
    cache = ContentCache(str(tmp_path), ttl=0)
    url = "https://example.com/x"
    payloads = [bytes([i]) * 5000 for i in range(1, 21)]

    def writer(data):
        cache.set(url, data)

    threads = [threading.Thread(target=writer, args=(p,)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stored = cache.get(url)
    # The stored value must be exactly one of the complete payloads (never a
    # torn mix of two writers).
    assert stored in payloads


def test_content_cache_stores_and_reads_meta(tmp_path):
    cache = ContentCache(str(tmp_path), ttl=0)
    cache.set("https://a", b"data", meta={"etag": '"v1"', "last_modified": None})
    assert cache.get_meta("https://a") == {"etag": '"v1"'}


def test_content_cache_get_stale_and_touch(tmp_path):
    cache = ContentCache(str(tmp_path), ttl=1)
    cache.set("https://a", b"data")
    path = cache._path("https://a")
    old = time.time() - 100
    os.utime(path, (old, old))
    assert cache.get("https://a") is None  # stale for ttl=1
    assert cache.get_stale("https://a") == b"data"
    cache.touch("https://a")
    assert cache.get("https://a") == b"data"  # fresh again


# ---------------------------------------------------------------------------
# Service-level conditional revalidation
# ---------------------------------------------------------------------------


def test_service_reuses_stale_on_upstream_304(tmp_path):
    settings = Settings(cache_dir=str(tmp_path), content_ttl=1)
    svc = FeedService(settings=settings)
    url = "https://example.com/news"
    svc.content_cache.set(url, b"old-bytes", meta={"etag": '"v1"'})
    path = svc.content_cache._path(url)
    old = time.time() - 100
    os.utime(path, (old, old))

    captured = {}

    def fake_fetch(u, user_agent=None, conditional=None, max_bytes=None):
        captured["conditional"] = conditional
        return None  # simulate 304 Not Modified

    svc.extractor.fetch = fake_fetch
    data = svc._fetch(url)
    assert data == b"old-bytes"
    assert captured["conditional"] == {"etag": '"v1"'}


def test_service_stores_new_content_when_changed(tmp_path):
    settings = Settings(cache_dir=str(tmp_path), content_ttl=1)
    svc = FeedService(settings=settings)
    url = "https://example.com/news"
    svc.content_cache.set(url, b"old", meta={"etag": '"v1"'})
    old = time.time() - 100
    os.utime(svc.content_cache._path(url), (old, old))

    svc.extractor.last_response_meta = {"etag": '"v2"'}

    def fake_fetch(u, user_agent=None, conditional=None, max_bytes=None):
        return b"new-bytes"

    svc.extractor.fetch = fake_fetch
    data = svc._fetch(url)
    assert data == b"new-bytes"
    assert svc.content_cache.get(url) == b"new-bytes"


# ---------------------------------------------------------------------------
# Server ETag / 304 and metrics endpoint
# ---------------------------------------------------------------------------


class _FakeSettings:
    content_ttl = 3600
    allowed_hosts = []


class _FakeService:
    settings = _FakeSettings()

    def get_feed(self, url, force_refresh=False):
        return {
            "title": "T",
            "language": "en",
            "link": url,
            "description": "T",
            "items": [
                {
                    "title": "a",
                    "description": "d",
                    "pubdate": None,
                    "unique_id": "1",
                    "link": url,
                    "extra": {"links": [], "images": []},
                }
            ],
        }


def _start_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.FeedRequestHandler)
    srv.feed_service = _FakeService()
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, srv.server_address[1]


def test_server_etag_and_conditional_304():
    srv, port = _start_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("GET", "/feed?url=http://example.com/news&format=json")
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 200
        etag = resp.getheader("ETag")
        assert etag
        assert resp.getheader("Last-Modified")

        conn.request(
            "GET",
            "/feed?url=http://example.com/news&format=json",
            headers={"If-None-Match": etag},
        )
        resp2 = conn.getresponse()
        resp2.read()
        assert resp2.status == 304
    finally:
        srv.shutdown()
        srv.server_close()


def test_server_metrics_endpoint_behaviour():
    srv, port = _start_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("GET", "/metrics")
        resp = conn.getresponse()
        resp.read()
        if server_mod._PROM_AVAILABLE:
            assert resp.status == 200
        else:
            assert resp.status == 404
    finally:
        srv.shutdown()
        srv.server_close()
