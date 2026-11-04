"""Time extraction of the offline corpus, first visit and with cached specs.

Usage:  python benchmarks/extraction_benchmark.py [--runs 5] [--pages DIR] [--profile 25]

Every page of ``tests/corpus`` (or the ``*.html`` files of ``--pages``) is
extracted through one shared ``FeedService``, without network access:

- ``first visit``: no caches, so each build analyses the page, applies the
  inferred spec and reads structured data;
- ``cached spec``: the spec cache is filled by a first pass, so each build
  only applies the spec, as ``watch`` and the feed server do.

The best and the median of ``--runs`` passes are printed per mode. With
``--profile N`` one more pass of each mode runs under cProfile and the N
functions with the most cumulative time are printed.
"""

# ruff: noqa: E402, I001 -- the source checkout is added before project imports.

from __future__ import annotations

import argparse
import cProfile
import datetime as dt
import json
import logging
import pstats
import statistics
import sys
import tempfile
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import qddate

from newsworker.service import FeedService
from newsworker.settings import Settings

CORPUS = Path(__file__).resolve().parents[1] / "tests" / "corpus"
MODES = (("first visit", False), ("cached spec", True))


def load_pages(pages_dir: Path | None) -> tuple[list[tuple[str, bytes]], dt.datetime]:
    if pages_dir is None:
        data = json.loads((CORPUS / "cases.json").read_text(encoding="utf-8"))
        now = dt.datetime.fromisoformat(data.get("now", "2025-10-16T12:00:00+00:00"))
        # Cases share listing URLs; a URL per case keeps one cached spec per page.
        pages = [
            (f"{case['url']}?case={index}", (CORPUS / case["page"]).read_bytes())
            for index, case in enumerate(data["cases"])
        ]
        return pages, now
    pages = [
        (f"https://example.com/{path.stem}", path.read_bytes())
        for path in sorted(pages_dir.glob("*.html"))
    ]
    return pages, dt.datetime.now(dt.timezone.utc)


def run_pass(service: FeedService, pages: list[tuple[str, bytes]]) -> tuple[float, int]:
    items = 0
    started = time.perf_counter()
    for url, data in pages:
        items += len(service.get_feed(url, data=data).get("items", []))
    return time.perf_counter() - started, items


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=5, help="Timed passes per mode (default 5).")
    parser.add_argument("--pages", type=Path, help="Directory of saved *.html pages to use.")
    parser.add_argument("--profile", type=int, default=0, metavar="N", help="Profile one pass.")
    args = parser.parse_args(argv)
    logging.disable(logging.WARNING)
    pages, now = load_pages(args.pages)
    print(f"qddate {qddate.__version__}, {len(pages)} pages, {args.runs} passes per mode")
    for label, cached in MODES:
        with tempfile.TemporaryDirectory(prefix="newsworker-benchmark-") as cache_dir:
            service = FeedService(
                Settings(cache_dir=cache_dir, respect_robots=False),
                use_cache=cached,
                plugins=[],
                bridges=[],
                clock=lambda: now,
            )
            run_pass(service, pages)  # warm-up: thread parsers, spec cache
            timings = []
            for _ in range(max(1, args.runs)):
                elapsed, items = run_pass(service, pages)
                timings.append(elapsed)
            per_page = 1000 * min(timings) / len(pages)
            print(
                f"{label:12}: best {min(timings):.3f} s, median {statistics.median(timings):.3f} s,"
                f" {per_page:.2f} ms/page, {items} items"
            )
            if args.profile:
                profile = cProfile.Profile()
                profile.runcall(run_pass, service, pages)
                stats = pstats.Stats(profile)
                stats.strip_dirs().sort_stats("cumulative").print_stats(args.profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
