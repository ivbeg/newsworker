# Change: Watch mode with pagination, deduplication, and webhook delivery

## Why
These four integration items interact and, per the audit, should be designed together:
following pagination for archives, deduplicating items across runs, delivering new items
via webhook, and a long-running watch loop. Together they turn `newsworker` into a
crawl-and-deliver component. (Audit E3, E4, E5, E6.)

## What Changes
- Pagination following: in `SpecExtractor`, detect a "next" link and recurse up to
  `--max-pages`.
- Cross-run deduplication: persist emitted `unique_id` hashes in a SQLite database; a new
  run emits only items not seen before.
- Webhook delivery: `--webhook https://...` POSTs new items as JSON.
- Watch mode: `newsworker watch URL --interval N` polls, emits/delivers new items, and
  exits cleanly on signal.

## Impact
- Affected specs: `feed-delivery`
- Affected code: `spec.py`/`extractor.py` (pagination), new `dedup` store (SQLite),
  new `watch` command in `core.py`, webhook client, `settings.py`
- Depends on: `enrich-feed-item-fields` (stable item identity) recommended first.
