"""Explicit URL, local-file, and standard-input document sources."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

from .tools import validate_url

#: Default cap on local input, matching the default ``max_content_bytes``.
DEFAULT_MAX_BYTES = 10 * 1024 * 1024


class DocumentSourceError(ValueError):
    pass


def _bounded_read(handle: BinaryIO, max_bytes: int, label: str) -> bytes:
    payload = handle.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise DocumentSourceError(f"{label} exceeds the {max_bytes}-byte input limit")
    return payload


@dataclass(frozen=True)
class DocumentSource:
    kind: str
    base_url: str
    location: Optional[str] = None
    data: Optional[bytes] = None

    @classmethod
    def url(cls, url: str) -> DocumentSource:
        validate_url(url)
        return cls(kind="url", base_url=url, location=url)

    @classmethod
    def file(
        cls, path: str, *, base_url: str, max_bytes: int = DEFAULT_MAX_BYTES
    ) -> DocumentSource:
        validate_url(base_url)
        target = Path(path).expanduser()
        if not target.is_file():
            raise DocumentSourceError(f"local source is not a readable regular file: {target}")
        with target.open("rb") as handle:
            payload = _bounded_read(handle, max_bytes, f"local source {target}")
        if not payload:
            raise DocumentSourceError(f"local source is empty: {target}")
        return cls(kind="file", base_url=base_url, location=str(target), data=payload)

    @classmethod
    def stdin(
        cls,
        *,
        base_url: str,
        stream: Optional[BinaryIO] = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> DocumentSource:
        validate_url(base_url)
        handle = stream or sys.stdin.buffer
        payload = _bounded_read(handle, max_bytes, "standard input")
        if not payload:
            raise DocumentSourceError("standard input is empty")
        return cls(kind="stdin", base_url=base_url, location="-", data=payload)

    @property
    def is_local(self) -> bool:
        return self.kind in {"file", "stdin"}
