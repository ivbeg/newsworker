"""Evidence levels for date, metadata, text and end-to-end language support."""

from __future__ import annotations

from dataclasses import dataclass


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
    "uk": "Ukrainian",
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
}


LANGUAGE_SUPPORT: dict[str, LanguageSupport] = {
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


_COLUMNS = (
    ("date", "Date"),
    ("metadata", "Metadata"),
    ("text", "Text"),
    ("extraction", "Extraction"),
)


def support_groups():
    """Languages grouped by identical support levels, best supported first."""
    groups: dict[tuple, list] = {}
    for entry in LANGUAGE_SUPPORT.values():
        levels = tuple(getattr(entry, key) for key, _ in _COLUMNS)
        groups.setdefault(levels, []).append(entry)
    rank = {"supported": 0, "partial": 1}
    return sorted(
        ((levels, sorted(entries, key=lambda e: e.name)) for levels, entries in groups.items()),
        key=lambda group: (
            rank.get(group[0][3], 2),
            -sum(level == "tested" for level in group[0]),
            group[1][0].name,
        ),
    )


def support_markdown() -> str:
    """The support matrix as the Markdown table shown in the documentation."""
    header = "| Language | " + " | ".join(title for _, title in _COLUMNS) + " |"
    lines = [header, "| --- |" + " --- |" * len(_COLUMNS)]
    for levels, entries in support_groups():
        names = ", ".join(f"{e.name} (`{e.code}`)" for e in entries)
        lines.append(f"| {names} | " + " | ".join(levels) + " |")
    return "\n".join(lines) + "\n"
