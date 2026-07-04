"""Tests for TLS verification defaults and robots.txt compliance."""

from urllib.robotparser import RobotFileParser

import pytest

from newsworker import tools
from newsworker.extractor import FeedExtractor
from newsworker.settings import Settings
from newsworker.tools import can_fetch, clear_robots_cache


ROBOTS_TXT = """
User-agent: *
Disallow: /private/

User-agent: blockedbot
Disallow: /
""".strip()


def _seed_robots(root, body):
    """Populates the robots cache with parsed ``body`` for ``root`` (no network)."""
    parser = RobotFileParser()
    parser.parse(body.splitlines())
    tools._ROBOTS_CACHE[root] = parser


@pytest.fixture(autouse=True)
def _clear_robots():
    clear_robots_cache()
    yield
    clear_robots_cache()


def test_can_fetch_allows_permitted_path():
    _seed_robots("https://example.com", ROBOTS_TXT)
    assert can_fetch("https://example.com/news", user_agent="newsworker") is True


def test_can_fetch_blocks_disallowed_path():
    _seed_robots("https://example.com", ROBOTS_TXT)
    assert can_fetch("https://example.com/private/x", user_agent="newsworker") is False


def test_can_fetch_blocks_agent_specific_rule():
    _seed_robots("https://example.com", ROBOTS_TXT)
    assert can_fetch("https://example.com/news", user_agent="blockedbot") is False


def test_can_fetch_is_lenient_when_robots_unavailable():
    # A cached None means robots.txt could not be read -> allow.
    tools._ROBOTS_CACHE["https://example.com"] = None
    assert can_fetch("https://example.com/anything") is True


class _FakeResponse:
    def __init__(self):
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=65536):
        return iter([b"<html>ok</html>"])


def test_fetch_refuses_disallowed_url_before_request():
    _seed_robots("https://example.com", ROBOTS_TXT)
    ext = FeedExtractor(filtered_text_length=150, respect_robots=True)
    called = {"get": False}

    def _get(*a, **k):
        called["get"] = True
        return _FakeResponse()

    ext.http_session.get = _get
    with pytest.raises(PermissionError):
        ext.fetch("https://example.com/private/secret", user_agent="newsworker")
    assert called["get"] is False


def test_fetch_passes_verify_flag_from_settings():
    ext = FeedExtractor(filtered_text_length=150, respect_robots=False, verify_tls=True)
    captured = {}

    def _get(url, **kwargs):
        captured.update(kwargs)
        return _FakeResponse()

    ext.http_session.get = _get
    ext.fetch("https://example.com/news")
    assert captured.get("verify") is True

    ext.verify_tls = False
    ext.fetch("https://example.com/news")
    assert captured.get("verify") is False


def test_settings_defaults_are_secure():
    s = Settings()
    assert s.verify_tls is True
    assert s.respect_robots is True
