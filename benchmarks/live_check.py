"""Check extraction against a few live public news pages (network required).

Usage:  python benchmarks/live_check.py [sources.json]

Fails when a source yields fewer items than its ``min_items``, when items lack
dates, or when every item links back to the listing page (a sign that the
headline links were not found). Used by the scheduled ``network-smoke`` job.
"""

# ruff: noqa: E402, I001 -- the source checkout is added before project imports.

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from newsworker.service import FeedService
from newsworker.settings import Settings

SOURCES = Path(__file__).with_name("live_sources.json")


def check(path: Path = SOURCES) -> int:
    sources = json.loads(path.read_text(encoding="utf-8"))["sources"]
    failures = 0
    with tempfile.TemporaryDirectory() as cache_dir:
        service = FeedService(Settings(cache_dir=cache_dir), use_cache=False)
        for source in sources:
            url = source["url"]
            try:
                items = service.get_feed(url).get("items", [])
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {url}: {type(exc).__name__}: {exc}")
                failures += 1
                continue
            dated = sum(1 for item in items if item.get("pubdate"))
            distinct = {item.get("link") for item in items} - {url, None}
            problems = []
            if len(items) < source.get("min_items", 1):
                problems.append(f"{len(items)} items < {source['min_items']}")
            if items and dated < len(items):
                problems.append(f"{len(items) - dated} undated")
            if items and not distinct:
                problems.append("no item links")
            status = "FAIL" if problems else "ok"
            print(
                f"{status:4} {url}: {len(items)} items, {len(distinct)} links {'; '.join(problems)}"
            )
            failures += bool(problems)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(check(Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCES))
