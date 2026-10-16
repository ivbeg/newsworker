"""Offline extraction quality gate over the labelled corpus in tests/corpus.

Regenerate the corpus with ``python benchmarks/build_corpus.py`` and print the
full report with ``python benchmarks/corpus_report.py``.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "benchmarks"))

from corpus_report import run_corpus  # noqa: E402

CORPUS = pathlib.Path(__file__).parent / "corpus"


@pytest.fixture(scope="module")
def corpus_score():
    return run_corpus(CORPUS)


def test_corpus_totals_meet_the_quality_floor(corpus_score):
    summary = corpus_score.summary()
    assert summary["cases"] >= 200
    for metric in ("precision", "recall", "title_accuracy", "date_accuracy"):
        assert summary[metric] == 1.0, corpus_score.to_markdown()


def test_every_case_is_extracted_exactly(corpus_score):
    failures = [
        f"{case.name}: precision {case.precision:.2f}, recall {case.recall:.2f}, "
        f"titles {case.titles_correct}/{case.matched}, dates {case.dates_correct}/"
        f"{case.dates_expected}, missing {case.missing[:2]}, unexpected {case.unexpected[:2]}"
        for case in corpus_score.cases
        if (
            case.precision < 1.0
            or case.recall < 1.0
            or case.titles_correct < case.matched
            or case.dates_correct < case.dates_expected
        )
    ]
    assert not failures, "\n".join(failures)


def test_flat_sibling_listing_uses_heading_led_groups():
    from newsworker.spec import SpecAnalyzer

    page = (CORPUS / "pages" / "en-flat-iso.html").read_bytes()
    spec = SpecAnalyzer().analyze("https://news.example.org/en/news/", data=page)
    assert spec.items.group == "siblings"
    assert spec.items.selector == "h2.news"
    assert spec.to_dict()["items"]["group"] == "siblings"
