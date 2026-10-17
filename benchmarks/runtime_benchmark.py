"""Offline request-runtime benchmark; no network access is performed."""

# ruff: noqa: E402, I001 -- the source checkout is added before project imports.

from __future__ import annotations

import concurrent.futures
import statistics
import sys
import tempfile
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.spec import FeedSpec, FieldRule, ItemsRule


HTML = b"""<html><head><title>Benchmark</title></head><body>
<article><time datetime='2026-08-04T10:00:00Z'>now</time><a href='/a'>Headline alpha</a></article>
<article><time datetime='2026-08-03T10:00:00Z'>then</time><a href='/b'>Headline beta</a></article>
</body></html>"""
SPEC = FeedSpec(
    title="Benchmark",
    items=ItemsRule(selector="article"),
    fields={
        "date": FieldRule(selector="time", source="attr:datetime", required=True),
        "title": FieldRule(selector="a", source="text"),
        "link": FieldRule(selector="a", source="attr:href", absolute=True),
    },
)


def run_case(label, function, iterations=50, workers=8):
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        counts = list(pool.map(lambda index: function(index), range(iterations)))
    elapsed = time.perf_counter() - started
    assert counts == [2] * iterations
    return label, elapsed, iterations / elapsed


def main():
    with tempfile.TemporaryDirectory(prefix="newsworker-benchmark-") as cache_dir:
        settings = Settings(cache_dir=cache_dir, respect_robots=False)
        shared = FeedService(settings, use_cache=False, bridges=[])

        def shared_case(index):
            return len(
                shared.get_feed(f"https://example.com/{index}", data=HTML, explicit_spec=SPEC)[
                    "items"
                ]
            )

        def isolated_case(index):
            service = FeedService(settings, use_cache=False, bridges=[])
            return len(
                service.get_feed(f"https://example.com/{index}", data=HTML, explicit_spec=SPEC)[
                    "items"
                ]
            )

        samples = []
        for _ in range(3):
            samples.append(run_case("shared request contexts", shared_case))
        shared_rate = statistics.median(sample[2] for sample in samples)
        isolated = run_case("isolated service per build", isolated_case)
        print(f"shared request contexts: {shared_rate:.1f} builds/s (median of 3)")
        print(f"isolated service per build: {isolated[2]:.1f} builds/s")
        print(f"shared/isolated ratio: {shared_rate / isolated[2]:.2f}x")


if __name__ == "__main__":
    main()
