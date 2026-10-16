import json
import pathlib

from typer.testing import CliRunner

from newsworker.core import app
from newsworker.explain import explain, to_html, to_json, to_text
from newsworker.service import FeedService
from newsworker.settings import Settings

CORPUS = pathlib.Path(__file__).parent / "corpus" / "pages"
BASE = "https://news.example.org/en/news/"


def _service(tmp_path, **values):
    return FeedService(Settings(cache_dir=str(tmp_path), **values), use_cache=False)


def test_report_shows_the_chosen_date_group_among_competitors(tmp_path):
    page = (CORPUS / "en-busy-sidebar-long.html").read_bytes()
    report = explain(_service(tmp_path), BASE, data=page, source="file")
    assert len(report.items) == 6
    assert report.clusters[0].chosen and report.clusters[0].titles == 6
    assert any("aside" in cluster.container for cluster in report.clusters[1:])
    assert report.spec_yaml and "items:" in report.spec_yaml
    assert json.loads(to_json(report))["strategy"] == report.strategy
    assert "date groups: " in to_text(report)


def test_hints_for_a_page_without_dates(tmp_path):
    page = b"<html><body><p>Nothing dated here</p></body></html>"
    report = explain(_service(tmp_path), BASE, data=page, source="file")
    assert report.items == [] and report.clusters == []
    assert any("--render" in hint and "--undated" in hint for hint in report.hints)


def test_hint_when_items_link_to_the_listing_page(tmp_path):
    rows = "".join(
        f"<li><span>{day}.10.2025</span> Headline number {day} without its own link</li>"
        for day in range(10, 14)
    )
    page = f"<html><body><ul>{rows}</ul></body></html>".encode()
    report = explain(_service(tmp_path), BASE, data=page, source="file")
    assert report.items
    assert any("link to the listing page itself" in hint for hint in report.hints)


def test_html_report_escapes_page_content(tmp_path):
    rows = "".join(
        f"<li><span>{day}.10.2025</span> <a href='/n/{day}'>&lt;script&gt;alert({day})"
        f"&lt;/script&gt; headline text</a></li>"
        for day in range(10, 14)
    )
    page = f"<html><body><ul>{rows}</ul></body></html>".encode()
    html = to_html(explain(_service(tmp_path), BASE, data=page, source="file"))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "default-src 'none'" in html


def test_explain_command_writes_html(tmp_path):
    report = tmp_path / "report.html"
    config = tmp_path / "config.yaml"
    config.write_text(f"cache_dir: {tmp_path / 'cache'}\n")
    result = CliRunner().invoke(
        app,
        [
            "explain",
            "--file",
            str(CORPUS / "en-list-long.html"),
            "--base-url",
            BASE,
            "-f",
            "html",
            "-o",
            str(report),
            "-c",
            str(config),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Why newsworker extracted what it did" in report.read_text()
    bad = CliRunner().invoke(app, ["explain", "--file", "x.html", BASE])
    assert bad.exit_code != 0
