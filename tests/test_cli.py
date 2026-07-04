"""Tests for CLI helper logic and fetch-option plumbing."""

import datetime

import pytest
from typer.testing import CliRunner

from newsworker import __version__
from newsworker.core import (
    _apply_item_filters,
    _parse_headers,
    app,
)
from newsworker.extractor import FeedExtractor


runner = CliRunner()


def _feed():
    return {
        "title": "T",
        "items": [
            {"title": "a", "pubdate": datetime.datetime(2024, 1, 1), "unique_id": "1"},
            {"title": "b", "pubdate": datetime.datetime(2024, 6, 1), "unique_id": "2"},
            {"title": "c", "pubdate": datetime.datetime(2024, 12, 1), "unique_id": "3"},
            {"title": "d", "pubdate": None, "unique_id": "4"},
        ],
    }


def test_limit_caps_items():
    feed = _apply_item_filters(_feed(), limit=2)
    assert [i["unique_id"] for i in feed["items"]] == ["1", "2"]


def test_since_filters_older_and_excludes_undated():
    feed = _apply_item_filters(_feed(), since="2024-05-01")
    assert [i["unique_id"] for i in feed["items"]] == ["2", "3"]


def test_until_filters_newer():
    feed = _apply_item_filters(_feed(), until="2024-06-30")
    assert [i["unique_id"] for i in feed["items"]] == ["1", "2"]


def test_since_until_and_limit_combined():
    feed = _apply_item_filters(_feed(), since="2024-01-01", until="2024-12-31", limit=2)
    assert [i["unique_id"] for i in feed["items"]] == ["1", "2"]


def test_parse_headers_ok():
    assert _parse_headers(["Accept-Language: fr", "X-Token:abc"]) == {
        "Accept-Language": "fr",
        "X-Token": "abc",
    }


def test_parse_headers_rejects_malformed():
    with pytest.raises(Exception):
        _parse_headers(["no-colon-here"])


def test_version_flag_prints_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


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


def test_fetch_forwards_proxy_headers_timeout():
    ext = FeedExtractor(
        filtered_text_length=150,
        respect_robots=False,
        timeout=7,
        proxy="http://proxy:3128",
        extra_headers={"X-Env": "test"},
    )
    captured = {}

    def _get(url, **kwargs):
        captured.update(kwargs)
        captured["url"] = url
        return _FakeResponse()

    ext.http_session.get = _get
    ext.fetch("https://example.com/news", user_agent="MyBot/1.0")

    assert captured["timeout"] == 7
    assert captured["proxies"] == {"http": "http://proxy:3128", "https": "http://proxy:3128"}
    assert captured["headers"]["X-Env"] == "test"
    assert captured["headers"]["User-agent"] == "MyBot/1.0"
