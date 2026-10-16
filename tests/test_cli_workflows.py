import datetime
import json
import logging

import pytest
from typer.testing import CliRunner

import newsworker.__main__ as entrypoint
from newsworker.core import (
    _configure_fetch_settings,
    _item_date,
    _JsonLogFormatter,
    _resolve_fetch_settings,
    app,
    enableJsonLogs,
)
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.spec import FeedSpec, FieldRule, ItemsRule

runner = CliRunner()

HTML = b"""<html lang='en'><head><meta charset='utf-8'><title>Local</title></head><body>
<article><time datetime='2026-08-04T10:00:00Z'>date</time><a href='/one'>First local headline</a></article>
<article><time datetime='2026-08-03T10:00:00Z'>date</time><a href='/two'>Second local headline</a></article>
</body></html>"""


def _spec(path):
    spec = FeedSpec(
        title="Local",
        items=ItemsRule(selector="article"),
        fields={
            "date": FieldRule(selector="time", source="attr:datetime", required=True),
            "title": FieldRule(selector="a", source="text"),
            "link": FieldRule(selector="a", source="attr:href", absolute=True),
        },
    )
    spec.save(str(path))
    return spec


def test_extract_local_workflow_output_and_diagnostics(tmp_path):
    source = tmp_path / "page.html"
    source.write_bytes(HTML)
    spec_path = tmp_path / "spec.yaml"
    output = tmp_path / "feed.json"
    _spec(spec_path)
    result = runner.invoke(
        app,
        [
            "extract",
            "--file",
            str(source),
            "--base-url",
            "https://example.com/archive/",
            "--spec",
            str(spec_path),
            "--format",
            "json",
            "--output",
            str(output),
            "--limit",
            "1",
            "--explain-json",
            "--no-cache",
            "--ignore-robots",
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(json.loads(output.read_text())["items"]) == 1
    assert '"chosen_strategy": "explicit_spec"' in result.stderr


def test_extract_local_stdout_human_explain_and_source_errors(tmp_path):
    source = tmp_path / "page.html"
    source.write_bytes(HTML)
    spec_path = tmp_path / "spec.yaml"
    _spec(spec_path)
    result = runner.invoke(
        app,
        [
            "extract",
            "--file",
            str(source),
            "--base-url",
            "https://example.com/",
            "--spec",
            str(spec_path),
            "--explain",
            "--format",
            "yaml",
        ],
    )
    assert result.exit_code == 0
    assert "strategy: explicit_spec" in result.stderr
    assert "items:" in result.stdout
    conflict = runner.invoke(app, ["extract", "https://example.com", "--file", str(source)])
    assert conflict.exit_code == 1
    unsupported = runner.invoke(app, ["extract", "https://example.com", "--format", "bad"])
    assert unsupported.exit_code == 2


def test_analyze_local_file_and_stdin_provenance(tmp_path, monkeypatch):
    source = tmp_path / "page.html"
    source.write_bytes(HTML)
    output = tmp_path / "generated.yaml"
    generated = _spec(tmp_path / "template.yaml")

    def analyze(self, url, data=None, user_agent=None, require_items=False):
        assert data == HTML and require_items
        generated.source_url = url
        return generated

    monkeypatch.setattr("newsworker.core.SpecAnalyzer.analyze", analyze)
    result = runner.invoke(
        app,
        [
            "analyze",
            "--file",
            str(source),
            "--base-url",
            "https://example.com/archive/",
            "--output",
            str(output),
            "--language",
            "fr",
            "--ignore-robots",
        ],
    )
    assert result.exit_code == 0
    assert "input_kind: file" in output.read_text()
    stdin_result = runner.invoke(
        app,
        ["analyze", "--file", "-", "--base-url", "https://example.com/stdin/"],
        input=HTML.decode("utf-8"),
    )
    assert stdin_result.exit_code == 0
    assert "input_kind: stdin" in stdin_result.stdout


def test_serve_and_scan_command_paths(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "newsworker.core.run_server",
        lambda settings: captured.update(settings=settings),
    )
    result = runner.invoke(
        app,
        [
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            "8899",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--content-ttl",
            "12",
            "--verbose",
        ],
    )
    assert result.exit_code == 0
    assert captured["settings"].port == 8899

    monkeypatch.setattr(
        "newsworker.core.FeedsFinder.find_feeds",
        lambda self, url, **kwargs: {
            "url": url,
            "items": [{"title": "Feed", "url": url + "/feed", "feedtype": "rss"}],
        },
    )
    output = tmp_path / "scan.json"
    scan = runner.invoke(
        app,
        [
            "scan",
            "https://example.com",
            "--sitemap",
            "--no-verify",
            "--max-workers",
            "2",
            "--output",
            str(output),
            "--verbose",
        ],
    )
    assert scan.exit_code == 0 and json.loads(output.read_text())["items"]
    assert runner.invoke(app, ["scan", "https://example.com", "--format", "bad"]).exit_code == 2


def test_batch_manifest_exit_policies_and_validation(tmp_path, monkeypatch):
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text("https://example.com/good\nhttps://example.com/bad\n")

    def get_feeds(self, urls, max_workers=4, force_refresh=False, use_async=None):
        return {
            urls[0]: {
                "title": "Good",
                "link": urls[0],
                "description": "Good",
                "language": "en",
                "items": [],
                "provenance": {
                    "strategy": "spec",
                    "elapsed_ms": 2,
                    "cache_state": "hit",
                    "confidence": 0.8,
                },
            },
            urls[1]: {
                "error": "https://user:secret@example.com failed",
                "error_type": "FetchError",
                "elapsed_ms": 3,
            },
        }

    monkeypatch.setattr(FeedService, "get_feeds", get_feeds)
    manifest = tmp_path / "manifest.json"
    common = [
        "batch",
        "--urls-file",
        str(urls_file),
        "--output-dir",
        str(tmp_path / "out"),
        "--manifest",
        str(manifest),
    ]
    strict = runner.invoke(app, common)
    assert strict.exit_code == 2
    records = json.loads(manifest.read_text())
    assert [record["status"] for record in records] == ["success", "failure"]
    assert "secret" not in records[1]["error"]
    partial = runner.invoke(app, [*common, "--failure-policy", "partial-success"])
    assert partial.exit_code == 0
    assert runner.invoke(app, ["batch"]).exit_code == 2
    assert runner.invoke(app, [*common, "--max-workers", "0"]).exit_code != 0
    assert runner.invoke(app, [*common, "--manifest-format", "xml"]).exit_code != 0


@pytest.mark.parametrize(
    "args",
    [
        ["watch", "https://example.com", "--interval", "0"],
        ["watch", "https://example.com", "--max-pages", "0"],
        ["watch", "https://example.com", "--max-iterations", "-1"],
        ["watch", "https://example.com", "--channel", "missing"],
        ["watch", "https://example.com", "--format", "bad"],
    ],
)
def test_watch_rejects_invalid_runtime_options(args):
    assert runner.invoke(app, args).exit_code != 0


def test_entrypoint_exit_interrupt_and_error(monkeypatch, capsys):
    monkeypatch.setattr("newsworker.core.cli", lambda: 7)
    with pytest.raises(SystemExit) as exited:
        entrypoint.main()
    assert exited.value.code == 7

    monkeypatch.setattr("newsworker.core.cli", lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(SystemExit) as interrupted:
        entrypoint.main()
    assert interrupted.value.code == 130
    assert "Ctrl-C" in capsys.readouterr().out

    monkeypatch.setattr("newsworker.core.cli", lambda: (_ for _ in ()).throw(RuntimeError("bad")))
    with pytest.raises(SystemExit) as failed:
        entrypoint.main()
    assert failed.value.code == 1
    assert "Error: bad" in capsys.readouterr().err


def test_cli_configuration_and_logging_helper_branches(tmp_path):
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", (), None)
    assert json.loads(_JsonLogFormatter().format(record))["message"] == "hello"
    enableJsonLogs()
    assert all(
        isinstance(handler.formatter, _JsonLogFormatter) for handler in logging.root.handlers
    )

    cookie = tmp_path / "cookies.txt"
    cookie.write_text("# Netscape HTTP Cookie File\n")
    settings = _configure_fetch_settings(
        Settings(),
        user_agent="agent",
        insecure=True,
        ignore_robots=True,
        timeout=4,
        proxy="http://proxy.example",
        header=["X-Test: yes"],
        cookies=str(cookie),
        language="de",
    )
    assert settings.cookies_file == str(cookie) and settings.default_language == "de"
    resolved = _resolve_fetch_settings(
        None,
        user_agent="agent",
        insecure=True,
        ignore_robots=True,
        timeout=4,
        proxy="http://proxy.example",
        header=["X-Test: yes"],
        cookies=str(cookie),
        language="de",
    )
    assert resolved.verify_tls is False and resolved.extra_headers == {"X-Test": "yes"}
    assert _item_date({"pubdate": datetime.date(2026, 1, 2)}) == datetime.date(2026, 1, 2)
    assert _item_date({"pubdate": "bad"}) is None


def test_additional_cli_success_and_failure_paths(tmp_path, monkeypatch):
    invalid_spec = tmp_path / "invalid.yaml"
    invalid_spec.write_text("version: 99\n")
    invalid = runner.invoke(app, ["spec", "validate", str(invalid_spec)])
    assert invalid.exit_code == 1 and "invalid:" in invalid.stderr

    config = tmp_path / "config.yaml"
    config.write_text(f"cache_dir: {tmp_path / 'cache'}\n")
    listed = runner.invoke(app, ["cache", "list", "--config", str(config)])
    assert listed.exit_code == 0 and "[content]" in listed.stdout
    parsed = runner.invoke(app, ["parsedate", "4 July 2026", "--verbose"])
    assert parsed.exit_code == 0

    monkeypatch.setattr(
        "newsworker.core.run_server", lambda settings: (_ for _ in ()).throw(RuntimeError("bind"))
    )
    assert runner.invoke(app, ["serve", "--verbose"]).exit_code == 1
    monkeypatch.setattr(
        "newsworker.core.FeedsFinder.find_feeds",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("scan")),
    )
    assert runner.invoke(app, ["scan", "https://example.com", "--verbose"]).exit_code == 1
