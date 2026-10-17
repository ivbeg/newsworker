"""Spec validation, local document sources and extraction diagnostics."""

import io

import pytest
from lxml.html import fromstring

from newsworker.diagnostics import ExtractionDiagnostics, diagnostics_text
from newsworker.language import LANGUAGE_SUPPORT, support_for
from newsworker.sources import DocumentSource, DocumentSourceError
from newsworker.spec import FeedSpec, SpecValidationError, validate_spec_dict
from newsworker.tools import resolve_feed_language_with_diagnostics


def test_spec_validation_precise_errors():
    with pytest.raises(SpecValidationError, match="unsupported spec version"):
        validate_spec_dict({"version": 2})
    with pytest.raises(SpecValidationError, match="items.selector_type"):
        validate_spec_dict({"version": 1, "items": {"selector_type": "regex"}})
    with pytest.raises(SpecValidationError, match="fields.title.source"):
        validate_spec_dict(
            {
                "version": 1,
                "items": {"selector": "article"},
                "fields": {"title": {"source": "magic"}},
            }
        )
    assert FeedSpec().validate() is not None


def test_document_sources_file_stdin_and_errors(tmp_path):
    path = tmp_path / "page.html"
    path.write_bytes(b"<html><a href='/x'>x</a></html>")
    source = DocumentSource.file(str(path), base_url="https://example.com/archive")
    assert source.is_local and source.data.startswith(b"<html")
    stdin = DocumentSource.stdin(
        base_url="https://example.com/base", stream=io.BytesIO(b"<html>stdin</html>")
    )
    assert stdin.kind == "stdin"
    assert DocumentSource.url("https://example.com").kind == "url"
    with pytest.raises(DocumentSourceError, match="regular file"):
        DocumentSource.file(str(tmp_path / "missing"), base_url="https://example.com")
    with pytest.raises(DocumentSourceError, match="empty"):
        DocumentSource.stdin(base_url="https://example.com", stream=io.BytesIO())


def test_diagnostics_score_serialize_and_text():
    diagnostic = ExtractionDiagnostics(source="file", requested_url="https://e")
    diagnostic.start("parse")
    diagnostic.stop("parse")
    diagnostic.add_attempt("spec", "success", item_count=3, selectors={"items": "article"})
    feed = {
        "items": [
            {"title": "a", "link": "https://e/a", "pubdate": "date"},
            {"title": "b", "link": "https://e/b", "pubdate": "date"},
            {"title": "c", "link": "https://e/c", "pubdate": "date"},
        ]
    }
    assert diagnostic.score(feed) == 1.0
    diagnostic.chosen_strategy = "spec"
    assert diagnostic.to_dict()["attempts"][0]["strategy"] == "spec"
    assert "confidence: 1.000" in diagnostics_text(diagnostic)
    empty = ExtractionDiagnostics()
    assert empty.score({"items": []}) == 0
    assert "No items" in empty.warnings[0]


def test_language_override_and_ambiguous_diagnostics():
    language, details = resolve_feed_language_with_diagnostics(override="fr-FR")
    assert (language, details["reason"]) == ("fr", "explicit_override")
    language, details = resolve_feed_language_with_diagnostics()
    assert language == "en" and details["ambiguous"] is True
    doc = fromstring("<html lang='en'><body></body></html>")
    _, details = resolve_feed_language_with_diagnostics(
        document=doc, text_samples=["Важная новость экономики России сегодня"]
    )
    assert details["reason"] == "ambiguous_evidence"
    assert support_for("fr-FR").extraction == "supported"
    assert LANGUAGE_SUPPORT["ja"].extraction == "partial"
