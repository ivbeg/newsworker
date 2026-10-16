"""Typed per-source batch results and deterministic manifest writers."""

from __future__ import annotations

import csv
import dataclasses
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BatchResult:
    source: str
    status: str
    output_path: str | None = None
    elapsed_ms: float = 0.0
    transport: str = "thread"
    cache_state: str | None = None
    strategy: str | None = None
    item_count: int = 0
    confidence: float | None = None
    warnings: list[str] = field(default_factory=list)
    error_type: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"success", "partial", "failure"}:
            raise ValueError("batch status must be success, partial, or failure")
        self.error = redact_batch_error(self.error)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def write_manifest(records: Iterable[BatchResult], path: str, fmt: str = "json") -> None:
    rows = [record.to_dict() for record in records]
    if fmt == "json":
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2, ensure_ascii=False)
        return
    if fmt == "csv":
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(BatchResult.__dataclass_fields__))
            writer.writeheader()
            for row in rows:
                row["warnings"] = json.dumps(row["warnings"], ensure_ascii=False)
                writer.writerow(row)
        return
    raise ValueError("manifest format must be json or csv")


def redact_batch_error(error: str | None) -> str | None:
    if error is None:
        return None
    text = str(error)
    text = re.sub(r"(https?://)([^/@\s]+)@", r"\1<redacted>@", text)
    text = re.sub(r"(?i)([?&](?:token|key|secret|password)=)[^&\s]+", r"\1<redacted>", text)
    text = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1<redacted>", text)
    return text[:1000]
