"""Signed /feed links let RSS readers subscribe to a protected server."""

from urllib.parse import parse_qs, urlsplit

import pytest
from test_server_controls import request, start_server
from typer.testing import CliRunner

from newsworker.core import app
from newsworker.server import feed_signature, public_feed_url
from newsworker.settings import Settings, SettingsError

KEY = "k" * 32
SOURCE = "https://example.org/news"


def _path(url):
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}"


def test_signed_link_authorises_exactly_one_feed(tmp_path):
    settings = Settings(cache_dir=str(tmp_path), feed_signing_key=KEY, port=8787)
    link = public_feed_url(settings, SOURCE, "rss")
    assert parse_qs(urlsplit(link).query)["sig"] == [feed_signature(KEY, SOURCE, "rss")]
    server = start_server(settings)
    try:
        assert request(server, "GET", _path(link))[0] == 200
        other_format = _path(link).replace("format=rss", "format=atom")
        assert request(server, "GET", other_format)[0] == 401
        other_page = _path(link).replace("news", "other")
        assert request(server, "GET", other_page)[0] == 401
        unsigned = "/feed?url=https%3A%2F%2Fexample.org%2Fnews&format=rss"
        assert request(server, "GET", unsigned)[0] == 401
        # The key protects /feed only; /metrics follows api_tokens as before.
        assert request(server, "GET", "/metrics")[0] != 401
    finally:
        server.shutdown()
        server.server_close()


def test_tokens_still_work_alongside_signatures(tmp_path):
    settings = Settings(cache_dir=str(tmp_path), feed_signing_key=KEY, api_tokens=["t" * 20])
    server = start_server(settings)
    try:
        unsigned = "/feed?url=https%3A%2F%2Fexample.org%2Fnews"
        assert request(server, "GET", unsigned)[0] == 401
        assert request(server, "GET", unsigned, {"Authorization": "Bearer " + "t" * 20})[0] == 200
    finally:
        server.shutdown()
        server.server_close()


def test_self_link_in_a_signed_feed_is_the_signed_link(tmp_path):
    settings = Settings(
        cache_dir=str(tmp_path), feed_signing_key=KEY, public_base_url="https://feeds.example"
    )
    link = public_feed_url(settings, SOURCE, "atom")
    server = start_server(settings)
    try:
        status, _headers, body = request(server, "GET", _path(link))
        assert status == 200
        assert link.replace("&", "&amp;") in body.decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()


def test_short_signing_keys_are_rejected():
    with pytest.raises(SettingsError):
        Settings(feed_signing_key="short").validate()


def test_feed_url_command(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(f"feed_signing_key: {KEY}\npublic_base_url: https://feeds.example\n")
    result = CliRunner().invoke(app, ["feed-url", SOURCE, "-f", "rss", "-c", str(config)])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == public_feed_url(
        Settings(feed_signing_key=KEY, public_base_url="https://feeds.example"), SOURCE, "rss"
    )
