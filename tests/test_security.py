import pytest

from newsworker.extractor import FeedExtractor
from newsworker.tools import validate_url


def test_validate_url_accepts_http_https():
    assert validate_url("http://example.com/x")
    assert validate_url("https://example.com/x")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://example.com",
        "javascript:alert(1)",
        "",
    ],
)
def test_validate_url_rejects_non_http_schemes(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_validate_url_requires_host():
    with pytest.raises(ValueError):
        validate_url("http:///nohost")


def test_validate_url_allowed_hosts_allows_member():
    assert validate_url("https://example.com/x", allowed_hosts=["example.com"])


def test_validate_url_allowed_hosts_blocks_non_member():
    with pytest.raises(ValueError):
        validate_url("https://evil.com/x", allowed_hosts=["example.com"])


def test_validate_url_allowed_hosts_case_insensitive():
    assert validate_url("https://Example.COM/x", allowed_hosts=["example.com"])


class _FakeResponse:
    """Minimal stand-in for a streamed requests.Response."""

    def __init__(self, chunks, headers=None):
        self._chunks = chunks
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=65536):
        return iter(self._chunks)


def _extractor_with_fake_get(chunks, headers=None):
    # These tests exercise the size-cap logic, not robots.txt; disable the
    # robots check so no real network read of /robots.txt is attempted.
    ext = FeedExtractor(
        filtered_text_length=150, max_bytes=100, respect_robots=False
    )
    ext.http_session.get = lambda *a, **k: _FakeResponse(chunks, headers)
    return ext


def test_fetch_returns_small_body():
    ext = _extractor_with_fake_get([b"<html>", b"ok</html>"])
    data = ext.fetch("https://example.com/news")
    assert data == b"<html>ok</html>"


def test_fetch_aborts_when_stream_exceeds_cap():
    # Two 80-byte chunks exceed the 100-byte cap mid-stream.
    ext = _extractor_with_fake_get([b"x" * 80, b"y" * 80])
    with pytest.raises(ValueError):
        ext.fetch("https://example.com/news")


def test_fetch_rejects_oversized_content_length():
    ext = _extractor_with_fake_get([b"small"], headers={"Content-Length": "999999"})
    with pytest.raises(ValueError):
        ext.fetch("https://example.com/news")


def test_fetch_rejects_bad_scheme_before_request():
    ext = FeedExtractor(filtered_text_length=150)
    with pytest.raises(ValueError):
        ext.fetch("file:///etc/passwd")
