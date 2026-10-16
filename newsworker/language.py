"""Evidence levels for date, metadata, text and end-to-end language support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class LanguageSupport:
    code: str
    name: str
    date: str
    metadata: str
    text: str
    extraction: str
    evidence: str


_DATE_LANGUAGES = {
    "en": "English",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "es": "Spanish",
}
_TEXT_ONLY = {
    "ar": "Arabic",
    "el": "Greek",
    "he": "Hebrew",
    "hi": "Hindi",
    "ja": "Japanese",
    "ko": "Korean",
    "th": "Thai",
    "zh": "Chinese",
    "bg": "Bulgarian",
    "cs": "Czech",
    "uk": "Ukrainian",
}


LANGUAGE_SUPPORT: Dict[str, LanguageSupport] = {
    code: LanguageSupport(
        code,
        name,
        date="tested",
        metadata="tested",
        text="tested" if code in {"en", "fr", "de", "pt", "ru", "es", "uk"} else "metadata-only",
        extraction="supported",
        evidence="tests/fixtures/languages/matrix.json",
    )
    for code, name in _DATE_LANGUAGES.items()
}
LANGUAGE_SUPPORT.update(
    {
        code: LanguageSupport(
            code,
            name,
            date="unsupported",
            metadata="tested",
            text="tested",
            extraction="partial",
            evidence="tests/test_date_language.py",
        )
        for code, name in _TEXT_ONLY.items()
    }
)


def support_for(code: str) -> LanguageSupport | None:
    return LANGUAGE_SUPPORT.get(code.lower().split("-", 1)[0])
