"""Credential scoping, connection-time address checks and parallel sessions."""

import concurrent.futures
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from newsworker.fetch import (
    AddressPolicyError,
    FetchPolicy,
    FetchRequest,
    RequestsTransport,
    policy_from_settings,
)
from newsworker.settings import Settings


class _Handler(BaseHTTPRequestHandler):
    seen = []
    delay = 0.0

    def log_message(self, *_args):
        pass

    def do_GET(self):
        type(self).seen.append((self.path, dict(self.headers)))
        if self.path.startswith("/redirect-cross"):
            port = self.server.server_address[1]
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{port}/landing")
            self.end_headers()
            return
        if self.path.startswith("/redirect-same"):
            self.send_response(302)
            self.send_header("Location", "/landing")
            self.end_headers()
            return
        if self.path.startswith("/slow"):
            time.sleep(type(self).delay)
        body = b"<html>ok</html>"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    _Handler.seen = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _local_policy(**overrides):
    values = dict(block_private_hosts=False, timeout=5)
    values.update(overrides)
    return FetchPolicy(**values)


def test_cross_origin_redirect_drops_credentials(server):
    port = server.server_address[1]
    policy = _local_policy(extra_headers={"Authorization": "Bearer secret", "X-Site-Token": "t"})
    RequestsTransport().fetch(
        FetchRequest(f"http://127.0.0.1:{port}/redirect-cross", headers={"Cookie": "a=b"}), policy
    )
    first, landing = _Handler.seen
    assert first[1].get("Authorization") == "Bearer secret"
    assert "Authorization" not in landing[1]
    assert "Cookie" not in landing[1]
    assert "X-Site-Token" not in landing[1]
    assert {k.lower(): v for k, v in landing[1].items()}["user-agent"] == "newsworker"


def test_same_origin_redirect_keeps_credentials(server):
    port = server.server_address[1]
    policy = _local_policy(extra_headers={"Authorization": "Bearer secret"})
    RequestsTransport().fetch(FetchRequest(f"http://127.0.0.1:{port}/redirect-same"), policy)
    assert _Handler.seen[-1][1].get("Authorization") == "Bearer secret"


def test_delivery_policy_does_not_inherit_source_headers():
    settings = Settings(extra_headers={"Authorization": "Bearer source-secret"})
    assert dict(policy_from_settings(settings).extra_headers) == {
        "Authorization": "Bearer source-secret"
    }
    assert dict(policy_from_settings(settings, operation="delivery").extra_headers) == {}


def test_dns_rebinding_to_private_address_is_blocked(server, monkeypatch):
    """Validation sees a public address, the connection gets loopback."""
    port = server.server_address[1]
    real_getaddrinfo = socket.getaddrinfo
    calls = {"n": 0}

    def rebinding(host, *args, **kwargs):
        if host == "rebind.example":
            calls["n"] += 1
            address = "93.184.216.34" if calls["n"] == 1 else "127.0.0.1"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", rebinding)
    with pytest.raises(AddressPolicyError):
        RequestsTransport().fetch(
            FetchRequest(f"http://rebind.example:{port}/"), FetchPolicy(timeout=5)
        )
    assert calls["n"] >= 2
    assert _Handler.seen == []


def test_allow_listed_private_host_may_connect(server):
    port = server.server_address[1]
    policy = FetchPolicy(timeout=5, allowed_hosts=("127.0.0.1",), allow_private_hosts=True)
    result = RequestsTransport().fetch(FetchRequest(f"http://127.0.0.1:{port}/"), policy)
    assert result.status == 200


def test_environment_proxy_is_ignored_by_default(server, monkeypatch):
    port = server.server_address[1]
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("NO_PROXY", "")
    result = RequestsTransport().fetch(FetchRequest(f"http://127.0.0.1:{port}/"), _local_policy())
    assert result.status == 200


def test_concurrent_fetches_run_in_parallel(server):
    port = server.server_address[1]
    _Handler.delay = 0.3
    transport = RequestsTransport()
    policy = _local_policy()
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda i: transport.fetch(
                    FetchRequest(f"http://127.0.0.1:{port}/slow/{i}"), policy
                ),
                range(4),
            )
        )
    _Handler.delay = 0.0
    assert time.monotonic() - started < 1.0
