"""Tests for cache stats/list/clear helpers and the `cache` CLI subcommand."""

import os

from typer.testing import CliRunner

from newsworker.cache import ContentCache
from newsworker.core import app
from newsworker.settings import Settings


runner = CliRunner()


def test_content_cache_stats_and_clear(tmp_path):
    cache = ContentCache(str(tmp_path), ttl=0)
    assert cache.stats()["count"] == 0
    cache.set("https://a.example/x", b"hello")
    cache.set("https://b.example/y", b"world!!")
    stats = cache.stats()
    assert stats["count"] == 2
    assert stats["bytes"] == len(b"hello") + len(b"world!!")
    entries = cache.list_entries()
    assert len(entries) == 2
    assert all(os.path.exists(e["path"]) for e in entries)
    removed = cache.clear()
    assert removed == 2
    assert cache.stats()["count"] == 0


def _config_file(tmp_path):
    cfg = tmp_path / "config.yaml"
    settings = Settings(cache_dir=str(tmp_path / "cache"))
    settings.save(str(cfg))
    return str(cfg)


def test_cli_cache_stats_reports_both(tmp_path):
    cfg = _config_file(tmp_path)
    cache_dir = str(tmp_path / "cache")
    ContentCache(cache_dir).set("https://a.example", b"data")

    result = runner.invoke(app, ["cache", "stats", "--config", cfg])
    assert result.exit_code == 0
    assert "content:" in result.stdout
    assert "specs:" in result.stdout


def test_cli_cache_scope_content_only(tmp_path):
    cfg = _config_file(tmp_path)
    result = runner.invoke(app, ["cache", "stats", "--content", "--config", cfg])
    assert result.exit_code == 0
    assert "content:" in result.stdout
    assert "specs:" not in result.stdout


def test_cli_cache_clear(tmp_path):
    cfg = _config_file(tmp_path)
    cache_dir = str(tmp_path / "cache")
    ContentCache(cache_dir).set("https://a.example", b"data")

    result = runner.invoke(app, ["cache", "clear", "--content", "--config", cfg])
    assert result.exit_code == 0
    assert "Cleared 1 content entries" in result.stdout
    assert ContentCache(cache_dir).stats()["count"] == 0
