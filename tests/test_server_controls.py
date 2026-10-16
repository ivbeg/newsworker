import http.client
import json
import threading
from http.server import ThreadingHTTPServer

from newsworker.diagnostics import ExtractionDiagnostics
from newsworker.server import FeedRequestHandler, TokenBucketLimiter
from newsworker.settings import Settings


class ControlledService:
    def __init__(self, settings):
        self.settings = settings
        self.calls = 0

    def get_feed_with_diagnostics(self, url, force_refresh=False):
        self.calls += 1
        diagnostic = ExtractionDiagnostics(chosen_strategy="dynamic", confidence=0.75)
        diagnostic.warnings.append("review")
        return (
            {
                "title": "Controlled",
                "description": "Controlled",
                "language": "en",
                "link": url,
                "items": [],
            },
            diagnostic,
        )


def start_server(settings):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FeedRequestHandler)
    server.feed_service = ControlledService(settings)
    server.rate_limiter = TokenBucketLimiter(
        settings.rate_limit_per_minute, settings.rate_limit_burst
    )
    server.build_semaphore = threading.BoundedSemaphore(settings.max_concurrent_builds)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def request(server, method, path, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
    connection.request(method, path, headers=headers or {})
    response = connection.getresponse()
    body = response.read()
    result = response.status, dict(response.getheaders()), body
    connection.close()
    return result


def test_health_readiness_index_and_problem_responses(tmp_path):
    settings = Settings(cache_dir=str(tmp_path), metrics_enabled=False)
    server = start_server(settings)
    try:
        status, headers, body = request(server, "GET", "/health/live")
        assert status == 200 and json.loads(body)["status"] == "live"
        assert headers["X-Content-Type-Options"] == "nosniff"
        status, _, body = request(server, "GET", "/health/ready")
        assert status == 200 and json.loads(body)["status"] == "ready"
        assert request(server, "GET", "/")[0] == 200
        status, headers, body = request(server, "GET", "/missing")
        assert status == 404 and json.loads(body)["request_id"] == headers["X-Request-ID"]
        assert request(server, "GET", "/metrics")[0] == 404
    finally:
        server.shutdown()
        server.server_close()


def test_auth_feed_etag_diagnostics_and_cors(tmp_path):
    settings = Settings(
        cache_dir=str(tmp_path),
        api_tokens=["secret"],
        cors_allowed_origins=["https://app.example"],
    )
    server = start_server(settings)
    path = "/feed?url=https%3A%2F%2Fexample.com%2Fnews&format=html&diagnostics=1"
    try:
        status, _, body = request(server, "GET", path)
        assert status == 401 and b"secret" not in body
        auth = {
            "Authorization": "Bearer secret",
            "Origin": "https://app.example",
            "X-Request-ID": "caller-id",
        }
        status, headers, body = request(server, "GET", path, auth)
        assert status == 200 and headers["Access-Control-Allow-Origin"] == "https://app.example"
        assert headers["X-Request-ID"] == "caller-id"
        assert headers["X-Newsworker-Confidence"] == "0.750"
        assert "default-src 'none'" in headers["Content-Security-Policy"]
        assert headers["ETag"]
        conditional = dict(auth)
        conditional["If-None-Match"] = headers["ETag"]
        assert request(server, "GET", path, conditional)[0] == 304
        assert request(server, "GET", "/feed", auth)[0] == 400
        assert request(server, "GET", "/feed?url=file%3A%2F%2Fx", auth)[0] == 400
        assert (
            request(server, "GET", "/feed?url=https%3A%2F%2Fexample.com&format=nope", auth)[0]
            == 400
        )
        assert request(server, "OPTIONS", "/feed", {"Origin": "https://app.example"})[0] == 204
        assert request(server, "OPTIONS", "/feed", {"Origin": "https://evil.example"})[0] == 403
    finally:
        server.shutdown()
        server.server_close()


def test_rate_limiter_deterministic_refill():
    now = [0.0]
    limiter = TokenBucketLimiter(rate_per_minute=60, burst=1, clock=lambda: now[0])
    assert limiter.allow("client")[0]
    allowed, retry = limiter.allow("client")
    assert not allowed and retry == 1
    now[0] += 1
    assert limiter.allow("client")[0]
    assert TokenBucketLimiter(0).allow("any") == (True, 0)


def test_feed_build_saturation_returns_bounded_overload(tmp_path):
    settings = Settings(cache_dir=str(tmp_path), max_concurrent_builds=1)
    server = start_server(settings)
    assert server.build_semaphore.acquire(blocking=False)
    try:
        status, headers, body = request(
            server,
            "GET",
            "/feed?url=https%3A%2F%2Fexample.com%2Fnews&format=json",
        )
        assert status == 503
        assert headers["X-Request-ID"] == json.loads(body)["request_id"]
        assert server.feed_service.calls == 0
    finally:
        server.build_semaphore.release()
        server.shutdown()
        server.server_close()
