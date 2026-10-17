"""Run the offline extraction corpus and print a Markdown report.

Usage:  python benchmarks/corpus_report.py [--json] [--output report.md]

The CI ``corpus`` job appends this report to the GitHub step summary.
"""

# ruff: noqa: E402, I001 -- the source checkout is added before project imports.

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from newsworker.evaluation import CorpusScore, score_case
from newsworker.service import FeedService
from newsworker.settings import Settings

CORPUS = Path(__file__).resolve().parents[1] / "tests" / "corpus"


def run_corpus(corpus: Path = CORPUS) -> CorpusScore:
    cases = json.loads((corpus / "cases.json").read_text(encoding="utf-8"))["cases"]
    scores = []
    with tempfile.TemporaryDirectory() as cache_dir:
        settings = Settings(cache_dir=cache_dir, respect_robots=False)
        service = FeedService(settings=settings, use_cache=False, plugins=[], bridges=[])
        for case in cases:
            data = (corpus / case["page"]).read_bytes()
            try:
                feed = service.get_feed(case["url"], data=data)
                items = feed.get("items", [])
            except Exception as exc:  # noqa: BLE001
                logging.warning("%s failed: %s", case["name"], exc)
                items = []
            scores.append(score_case(case["name"], items, case["expected"]))
    return CorpusScore(scores)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="Print only the summary as JSON.")
    parser.add_argument("--output", help="Also write the Markdown report to this file.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.ERROR)
    result = run_corpus()
    if args.json:
        print(json.dumps(result.summary(), indent=2))
        return 0
    report = "## Extraction corpus\n\n" + result.to_markdown() + "\n"
    print(report)
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
