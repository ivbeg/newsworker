"""The opt-in ``legacy_tls_ciphers`` setting for servers without modern TLS suites."""

import shutil
import ssl
import subprocess
import threading
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests
from typer.testing import CliRunner

from newsworker.async_fetch import _ssl_context
from newsworker.core import _extractor_from_settings, _resolve_fetch_settings, app
from newsworker.fetch import (
    FetchError,
    FetchPolicy,
    FetchRequest,
    RequestsTransport,
    legacy_ssl_context,
    policy_from_settings,
    with_tls_hint,
)
from newsworker.finder import FeedsFinder
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.spec import SpecAnalyzer

#: A TLS 1.2 suite with static RSA key exchange, left out of Python's defaults.
LEGACY_SUITE = "AES256-GCM-SHA384"
HANDSHAKE_ERROR = (
    "HTTPSConnectionPool(host='old.example', port=443): Max retries exceeded "
    "(Caused by SSLError(SSLError(1, '[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] "
    "ssl/tls alert handshake failure (_ssl.c:1032)')))"
)


def _cipher_names(context):
    return {cipher["name"] for cipher in context.get_ciphers()}


@pytest.fixture
def legacy_server(tmp_path):
    """An HTTPS server on 127.0.0.1 that accepts only :data:`LEGACY_SUITE`."""
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("openssl command not available")
    key, cert = tmp_path / "key.pem", tmp_path / "cert.pem"
    subprocess.run(
        [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1"]
        + ["-subj", "/CN=localhost", "-keyout", str(key), "-out", str(cert)],
        check=True,
        capture_output=True,
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.set_ciphers(LEGACY_SUITE)
    except ssl.SSLError:
        pytest.skip("this OpenSSL build cannot offer static-RSA suites")
    context.load_cert_chain(cert, key)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"legacy ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


def test_legacy_context_adds_static_rsa_suites_and_keeps_verification():
    from urllib3.util.ssl_ import create_urllib3_context

    assert LEGACY_SUITE not in _cipher_names(create_urllib3_context())
    verifying = legacy_ssl_context(True)
    assert LEGACY_SUITE in _cipher_names(verifying)
    assert verifying.verify_mode == ssl.CERT_REQUIRED and verifying.check_hostname is True
    assert legacy_ssl_context(True) is verifying
    assert legacy_ssl_context(False).verify_mode == ssl.CERT_NONE


def test_requests_transport_needs_the_opt_in_for_legacy_servers(legacy_server):
    transport = RequestsTransport()
    # The test certificate is self-signed; cipher negotiation is what is under test.
    policy = FetchPolicy(block_private_hosts=False, verify_tls=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(FetchError, match="--legacy-tls-ciphers"):
            transport.fetch(FetchRequest(legacy_server), policy)
        legacy = FetchPolicy(block_private_hosts=False, verify_tls=False, legacy_tls_ciphers=True)
        result = transport.fetch(FetchRequest(legacy_server), legacy)
        assert result.status == 200 and result.body == b"legacy ok"
        # The legacy pool is keyed separately: a default request still refuses the suite.
        with pytest.raises(FetchError, match="HANDSHAKE_FAILURE"):
            transport.fetch(FetchRequest(legacy_server), policy)


def test_handshake_hint_only_for_handshake_failures_without_the_opt_in():
    hinted = with_tls_hint(HANDSHAKE_ERROR, FetchPolicy())
    assert hinted.startswith(HANDSHAKE_ERROR)
    assert "--legacy-tls-ciphers" in hinted and "legacy_tls_ciphers: true" in hinted
    assert with_tls_hint(HANDSHAKE_ERROR, FetchPolicy(legacy_tls_ciphers=True)) == HANDSHAKE_ERROR
    assert with_tls_hint("Connection refused", FetchPolicy()) == "Connection refused"


def test_requests_transport_adds_hint_to_ssl_errors():
    class FailingSession:
        def get(self, url, **kwargs):
            raise requests.exceptions.SSLError(HANDSHAKE_ERROR)

    with pytest.raises(FetchError, match="--legacy-tls-ciphers"):
        RequestsTransport(FailingSession()).fetch(
            FetchRequest("https://old.example/"), FetchPolicy(block_private_hosts=False)
        )


def test_async_ssl_context_offers_legacy_suites_on_request():
    assert _ssl_context(True) is None
    verifying = _ssl_context(True, legacy_ciphers=True)
    assert LEGACY_SUITE in _cipher_names(verifying)
    assert verifying.verify_mode == ssl.CERT_REQUIRED and verifying.check_hostname is True
    insecure = _ssl_context(False, legacy_ciphers=True)
    assert LEGACY_SUITE in _cipher_names(insecure) and insecure.check_hostname is False
    assert LEGACY_SUITE not in _cipher_names(_ssl_context(False))


def test_setting_reaches_every_policy(tmp_path):
    settings = Settings.resolve(
        str(tmp_path / "missing.yaml"),
        environ={
            "NEWSWORKER_LEGACY_TLS_CIPHERS": "true",
            "NEWSWORKER_CACHE_DIR": str(tmp_path / "cache"),
        },
    )
    assert settings.legacy_tls_ciphers is True
    assert Settings().legacy_tls_ciphers is False
    assert policy_from_settings(settings).legacy_tls_ciphers is True
    assert policy_from_settings(settings, operation="delivery").legacy_tls_ciphers is True
    assert FeedsFinder(settings).policy.legacy_tls_ciphers is True
    assert _extractor_from_settings(settings)._policy().legacy_tls_ciphers is True
    assert FeedService(settings).extractor._policy().legacy_tls_ciphers is True


def test_cli_flag_enables_legacy_ciphers(tmp_path, monkeypatch):
    config = str(tmp_path / "missing.yaml")
    assert _resolve_fetch_settings(config).legacy_tls_ciphers is False
    assert _resolve_fetch_settings(config, legacy_tls_ciphers=True).legacy_tls_ciphers is True

    seen = {}

    def fake_analyze(self, url, data=None, user_agent=None, require_items=False):
        seen["legacy"] = self.ext.legacy_tls_ciphers
        raise RuntimeError("stop after setup")

    monkeypatch.setattr(SpecAnalyzer, "analyze", fake_analyze)
    CliRunner().invoke(
        app, ["analyze", "https://example.com/news", "--legacy-tls-ciphers", "-c", config]
    )
    assert seen == {"legacy": True}
