"""Score extracted feeds against labelled expectations.

Used by the offline extraction corpus (``tests/corpus``) and handy for checking
a site spec: compare what newsworker extracted with what a person says the page
contains.  Items are matched by normalised link; titles and dates are then
compared only for matched items.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_SPACE = re.compile(r"\s+")


def _norm_link(link: str | None) -> str | None:
    if not link:
        return None
    parts = urlsplit(link.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def _norm_text(text: str | None) -> str:
    return _SPACE.sub(" ", text or "").strip().casefold()


def _date_of(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)[:10]


@dataclass
class CaseScore:
    """Counts for one labelled page."""

    name: str
    expected: int = 0
    extracted: int = 0
    matched: int = 0
    titles_correct: int = 0
    dates_correct: int = 0
    dates_expected: int = 0
    missing: list[str] = field(default_factory=list)
    unexpected: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return (
            self.matched / self.extracted if self.extracted else (1.0 if not self.expected else 0.0)
        )

    @property
    def recall(self) -> float:
        return self.matched / self.expected if self.expected else 1.0


def score_case(
    name: str, items: Iterable[Mapping[str, Any]], expected: Iterable[Mapping[str, Any]]
) -> CaseScore:
    """Compare extracted ``items`` with ``expected`` items for one page."""
    items = list(items)
    expected = list(expected)
    score = CaseScore(name=name, expected=len(expected), extracted=len(items))
    by_link: dict[str, Mapping[str, Any]] = {}
    for item in items:
        link = _norm_link(item.get("link"))
        if link and link not in by_link:
            by_link[link] = item
    seen = set()
    for want in expected:
        link = _norm_link(want.get("link"))
        got = by_link.get(link) if link else None
        if got is None or link in seen:
            score.missing.append(want.get("link") or want.get("title") or "?")
            continue
        seen.add(link)
        score.matched += 1
        if _norm_text(got.get("title")) == _norm_text(want.get("title")):
            score.titles_correct += 1
        if want.get("date"):
            score.dates_expected += 1
            if _date_of(got.get("pubdate")) == want["date"]:
                score.dates_correct += 1
    expected_links = {_norm_link(want.get("link")) for want in expected}
    score.unexpected = [
        str(item.get("link"))
        for item in items
        if _norm_link(item.get("link")) not in expected_links
    ]
    return score


@dataclass
class CorpusScore:
    """Micro-averaged totals over many cases."""

    cases: list[CaseScore]

    def _sum(self, attr: str) -> int:
        return sum(getattr(case, attr) for case in self.cases)

    @property
    def precision(self) -> float:
        extracted = self._sum("extracted")
        return self._sum("matched") / extracted if extracted else 0.0

    @property
    def recall(self) -> float:
        expected = self._sum("expected")
        return self._sum("matched") / expected if expected else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def title_accuracy(self) -> float:
        matched = self._sum("matched")
        return self._sum("titles_correct") / matched if matched else 0.0

    @property
    def date_accuracy(self) -> float:
        expected = self._sum("dates_expected")
        return self._sum("dates_correct") / expected if expected else 0.0

    def summary(self) -> dict[str, float]:
        return {
            "cases": len(self.cases),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "title_accuracy": round(self.title_accuracy, 4),
            "date_accuracy": round(self.date_accuracy, 4),
        }

    def to_markdown(self) -> str:
        lines = [
            "| Case | Expected | Extracted | Precision | Recall | Titles | Dates |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for case in sorted(self.cases, key=lambda c: (c.recall + c.precision, c.name)):
            lines.append(
                f"| {case.name} | {case.expected} | {case.extracted} | {case.precision:.2f} | "
                f"{case.recall:.2f} | {case.titles_correct}/{case.matched} | "
                f"{case.dates_correct}/{case.dates_expected} |"
            )
        totals = self.summary()
        lines.append(
            f"| **Total** | {self._sum('expected')} | {self._sum('extracted')} | "
            f"**{totals['precision']:.2f}** | **{totals['recall']:.2f}** | "
            f"{totals['title_accuracy']:.2f} | {totals['date_accuracy']:.2f} |"
        )
        return "\n".join(lines)
