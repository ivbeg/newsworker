"""Stable, serializable extraction diagnostics and heuristic confidence scores."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .settings import redact_settings


@dataclass(frozen=True)
class DiagnosticReason:
    code: str
    message: str
    weight: float = 0.0
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyDiagnostic:
    strategy: str
    status: str
    item_count: int = 0
    elapsed_ms: float = 0.0
    selectors: Mapping[str, str] = field(default_factory=dict)
    reasons: list[DiagnosticReason] = field(default_factory=list)


@dataclass
class ExtractionDiagnostics:
    version: int = 1
    source: str = "network"
    requested_url: str | None = None
    effective_url: str | None = None
    chosen_strategy: str | None = None
    confidence: float = 0.0
    attempts: list[StrategyDiagnostic] = field(default_factory=list)
    reasons: list[DiagnosticReason] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    _starts: dict[str, float] = field(default_factory=dict, repr=False)

    def start(self, name: str) -> None:
        self._starts[name] = time.monotonic()

    def stop(self, name: str) -> float:
        start = self._starts.pop(name, None)
        elapsed = (time.monotonic() - start) * 1000 if start is not None else 0.0
        self.timings_ms[name] = round(elapsed, 3)
        return elapsed

    def add_attempt(
        self,
        strategy: str,
        status: str,
        *,
        item_count: int = 0,
        elapsed_ms: float = 0.0,
        selectors: Mapping[str, str] | None = None,
        reasons: list[DiagnosticReason] | None = None,
    ) -> None:
        self.attempts.append(
            StrategyDiagnostic(
                strategy=strategy,
                status=status,
                item_count=item_count,
                elapsed_ms=round(elapsed_ms, 3),
                selectors=dict(selectors or {}),
                reasons=list(reasons or []),
            )
        )

    def score(self, feed: Mapping[str, Any]) -> float:
        items = list(feed.get("items", []) or [])
        reasons: list[DiagnosticReason] = []
        score = 0.0
        if len(items) >= 3:
            score += 0.25
            reasons.append(
                DiagnosticReason("repeated_items", "At least three repeated items", 0.25)
            )
        elif items:
            score += 0.1
            reasons.append(DiagnosticReason("few_items", "Only a small number of items", 0.1))
        if items:
            title_ratio = sum(bool(item.get("title")) for item in items) / len(items)
            link_ratio = sum(bool(item.get("link")) for item in items) / len(items)
            date_ratio = sum(item.get("pubdate") is not None for item in items) / len(items)
            score += 0.25 * title_ratio + 0.25 * link_ratio + 0.25 * date_ratio
            reasons.extend(
                [
                    DiagnosticReason(
                        "title_completeness",
                        "Title completeness",
                        0.25 * title_ratio,
                        {"ratio": title_ratio},
                    ),
                    DiagnosticReason(
                        "link_completeness",
                        "Link completeness",
                        0.25 * link_ratio,
                        {"ratio": link_ratio},
                    ),
                    DiagnosticReason(
                        "date_coherence",
                        "Publication date completeness",
                        0.25 * date_ratio,
                        {"ratio": date_ratio},
                    ),
                ]
            )
        else:
            self.warnings.append("No items were extracted")
            reasons.append(DiagnosticReason("zero_items", "No extraction strategy produced items"))
        self.confidence = round(max(0.0, min(1.0, score)), 3)
        self.reasons = reasons
        if items and self.confidence < 0.6:
            self.warnings.append("Low heuristic extraction confidence")
        return self.confidence

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data.pop("_starts", None)
        data["metadata"] = redact_settings(data.get("metadata", {}))
        return data


def diagnostics_text(diagnostics: ExtractionDiagnostics) -> str:
    lines = [
        f"source: {diagnostics.source}",
        f"strategy: {diagnostics.chosen_strategy or 'none'}",
        f"confidence: {diagnostics.confidence:.3f} (heuristic)",
    ]
    for attempt in diagnostics.attempts:
        lines.append(
            f"- {attempt.strategy}: {attempt.status}, {attempt.item_count} items, "
            f"{attempt.elapsed_ms:.1f} ms"
        )
    for warning in diagnostics.warnings:
        lines.append(f"warning: {warning}")
    return "\n".join(lines)
