import json
from pathlib import Path

from qddate import DateParser

from newsworker.language import LANGUAGE_SUPPORT
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.spec import FeedSpec, FieldRule, ItemsRule


def test_supported_language_fixture_matrix(tmp_path):
    path = Path(__file__).parent / "fixtures" / "languages" / "matrix.json"
    matrix = json.loads(path.read_text(encoding="utf-8"))
    parser = DateParser(generate=True)
    for fixture in matrix["languages"]:
        code = fixture["code"]
        assert LANGUAGE_SUPPORT[code].extraction == "supported"
        assert parser.match(fixture["positive"]), (code, fixture["positive"])
        assert not parser.match(fixture["negative"]), (code, fixture["negative"])
        # A month name without a day or year must not become a publication date.
        assert not parser.match(fixture["ambiguous"]), (code, fixture["ambiguous"])

        html = (
            f"<html lang='{code}'><head><meta charset='utf-8'><title>{code}</title></head><body>"
            f"<article><time>{fixture['positive']}</time>"
            f"<a href='/{code}'>{fixture['headline']}</a></article>"
            "</body></html>"
        ).encode("utf-8")
        spec = FeedSpec(
            title=code,
            language=code,
            items=ItemsRule(selector="article"),
            fields={
                "date": FieldRule(selector="time", source="text", required=True),
                "title": FieldRule(selector="a", source="text"),
                "link": FieldRule(selector="a", source="attr:href", absolute=True),
            },
        )
        service = FeedService(
            Settings(
                cache_dir=str(tmp_path / code),
                respect_robots=False,
                block_private_hosts=False,
                default_language=code,
            ),
            use_cache=False,
            bridges=[],
        )
        feed, diagnostics = service.get_feed_with_diagnostics(
            f"https://example.com/{code}", data=html, explicit_spec=spec
        )
        assert feed["language"] == code
        assert feed["items"][0]["title"] == fixture["headline"]
        assert feed["items"][0]["pubdate"].year == 2026
        assert diagnostics.chosen_strategy == "explicit_spec"


def test_partial_languages_do_not_claim_date_support():
    for code in ("bg", "cs", "ja", "zh"):
        assert LANGUAGE_SUPPORT[code].extraction == "partial"


def test_documented_matrix_is_generated_from_language_support():
    from pathlib import Path

    from newsworker.language import support_markdown

    page = Path(__file__).resolve().parents[1] / "docs/docs/guides/language-support.md"
    assert support_markdown() in page.read_text(encoding="utf-8"), (
        "Regenerate the table with: newsworker languages --format markdown"
    )


def test_languages_command_formats():
    import json

    from typer.testing import CliRunner

    from newsworker.core import app

    runner = CliRunner()
    text = runner.invoke(app, ["languages"])
    assert text.exit_code == 0
    assert text.output.splitlines()[1].startswith("de")
    rows = json.loads(runner.invoke(app, ["languages", "-f", "json"]).output)
    assert {row["code"]: row["extraction"] for row in rows}["ja"] == "partial"
    assert runner.invoke(app, ["languages", "-f", "xml"]).exit_code == 2
