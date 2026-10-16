import json

from typer.testing import CliRunner

import newsworker.core as core
from newsworker.watching import WatchIterationResult


def _config(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(json.dumps({"cache_dir": str(tmp_path / "cache")}))
    return str(config)


def test_watch_polls_every_source_and_isolates_failures(tmp_path, monkeypatch):
    sources = tmp_path / "sources.txt"
    sources.write_text("# news sites\nhttps://a.example/news\nhttps://b.example/news\n")
    calls = []

    def fake_iteration(service, url, fmt, dedup, webhook, max_pages, **kwargs):
        calls.append(url)
        if url.startswith("https://a."):
            raise ConnectionError("a is down")
        return WatchIterationResult([], discovered=1, delivered=1)

    monkeypatch.setattr(core, "_run_watch_iteration", fake_iteration)
    result = CliRunner().invoke(
        core.app,
        ["watch", "--urls-file", str(sources), "--max-iterations", "1", "-c", _config(tmp_path)],
    )
    assert calls == ["https://a.example/news", "https://b.example/news"]
    assert result.exit_code == 1
    assert "https://a.example/news" in result.output
    assert "https://b.example/news" not in result.output


def test_watch_merges_url_and_opml_sources(tmp_path, monkeypatch):
    opml = tmp_path / "subs.opml"
    opml.write_text(
        '<opml version="2.0"><body>'
        '<outline text="A" xmlUrl="https://a.example/rss" htmlUrl="https://a.example/"/>'
        '<outline text="B" xmlUrl="https://b.example/rss"/></body></opml>'
    )
    calls = []
    monkeypatch.setattr(
        core,
        "_run_watch_iteration",
        lambda service, url, *args, **kwargs: calls.append(url) or WatchIterationResult([]),
    )
    result = CliRunner().invoke(
        core.app,
        [
            "watch",
            "https://a.example/rss",
            "--from-opml",
            str(opml),
            "--max-iterations",
            "1",
            "-c",
            _config(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == ["https://a.example/rss", "https://b.example/rss"]


def test_watch_requires_a_source(tmp_path):
    result = CliRunner().invoke(
        core.app, ["watch", "--max-iterations", "1", "-c", _config(tmp_path)]
    )
    assert result.exit_code != 0
