"""Offline extraction quality gate over the labelled corpus in tests/corpus.

Regenerate the corpus with ``python benchmarks/build_corpus.py`` and print the
full report with ``python benchmarks/corpus_report.py``.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "benchmarks"))

from corpus_report import run_corpus  # noqa: E402

CORPUS = pathlib.Path(__file__).parent / "corpus"
FULLY_SUPPORTED = {"en", "ru", "de", "fr", "es", "it", "pt"}


def _qddate_reads_ukrainian_months():
    from qddate import DateParser

    return DateParser(generate=True).match("16 жовтня 2025") is not None


@pytest.fixture(scope="module")
def corpus_score():
    return run_corpus(CORPUS)


def test_corpus_totals_meet_the_quality_floor(corpus_score):
    summary = corpus_score.summary()
    assert summary["cases"] >= 180
    assert summary["precision"] >= 0.98, corpus_score.to_markdown()
    assert summary["recall"] >= 0.92, corpus_score.to_markdown()
    assert summary["title_accuracy"] >= 0.98, corpus_score.to_markdown()
    assert summary["date_accuracy"] >= 0.98, corpus_score.to_markdown()


def test_fully_supported_languages_extract_every_case_exactly(corpus_score):
    cases = json.loads((CORPUS / "cases.json").read_text(encoding="utf-8"))["cases"]
    language = {case["name"]: case["language"] for case in cases}
    style = {case["name"]: case["date_style"] for case in cases}
    ukrainian_words = _qddate_reads_ukrainian_months()
    failures = [
        f"{case.name}: precision {case.precision:.2f}, recall {case.recall:.2f}, "
        f"missing {case.missing[:2]}, unexpected {case.unexpected[:2]}"
        for case in corpus_score.cases
        if (
            language[case.name] in FULLY_SUPPORTED
            or (language[case.name] == "uk" and (style[case.name] != "long" or ukrainian_words))
        )
        and (case.precision < 1.0 or case.recall < 1.0 or case.titles_correct < case.matched)
    ]
    assert not failures, "\n".join(failures)


def test_flat_sibling_listing_uses_heading_led_groups():
    from newsworker.spec import SpecAnalyzer

    page = (CORPUS / "pages" / "en-flat-iso.html").read_bytes()
    spec = SpecAnalyzer().analyze("https://news.example.org/en/news/", data=page)
    assert spec.items.group == "siblings"
    assert spec.items.selector == "h2.news"
    assert spec.to_dict()["items"]["group"] == "siblings"
