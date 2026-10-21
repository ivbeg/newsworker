# Change: Read dates in the page's language, order and precision

## Why
newsworker finds news by repeated dates, so the way a date string becomes a
publication time decides what a feed says. A review of qddate and newsworker
(2026-10-21) found gaps that do not need a new qddate release:

- Every page is matched against all fourteen qddate languages, although the
  page language is known before any date is read. That costs time on every
  text node and lets a foreign month pattern win.
- qddate reads `05/06/2022` day first but `05/13/2022` (and `05/06/22`) month
  first, so one US listing can mix both orders.
- A date without a time becomes 00:00 in `default_timezone` and is then
  converted to UTC, so on a UTC+3 site "5 May" is `2022-05-04T21:00Z`: another
  day in every output. The item model cannot say that no time was known.
- `newsworker parsedate` prints the raw qddate match of a fresh parser, so it
  can disagree with `extract` (datelines, relative dates, offsets,
  plausibility).

## What Changes
- **Page language first**: dates are matched with a per-thread qddate parser
  for the page language (explicit override, page metadata or
  `Content-Language`), which also knows every numeric pattern. Text with
  letters that it cannot read is matched again with all languages. Each text
  is matched once per build. Pattern sessions (spec date `patterns`, cached
  patterns) narrow every parser in use and are always closed.
- **One day/month order per group of dates**: a cluster's (or a spec's items')
  numeric dates share one order, decided by a date with a number above 12,
  else by the page locale (`en-US` month first). Ambiguous dates are read again
  with qddate's other reading (`match_all`). `explain` shows each group's order
  and why.
- **Date precision**: `date_precision` (`day`/`minute`/`second`) on every item
  dated by a built-in strategy. A day-precision date is 00:00 UTC on its
  calendar day and is not shifted between time zones. JSON/YAML, CSV and JSON
  Feed (`_newsworker` extension) carry the precision; RSS/Atom keep the day;
  previews show the date alone; `explain` prints the precision.
- **`parsedate` through the extraction path**: `FeedExtractor.read_text` with
  `--json`, `--now`, `--timezone`, `--language` (defaults from settings); the
  report names the pattern, languages, order, precision, offset and UTC time;
  exit code 1 for text that is not a date.

## Impact
- Affected specs: `language-support`, `feed-extraction`, `extraction-diagnostics`,
  `output-contracts`, `cli`
- Affected code: `dates.py`, `relative.py`, `runtime.py`, `extractor.py`,
  `spec/execute.py`, `tools.py`, `structured.py`, `native.py`, `model.py`,
  `formats.py`, `mcp_server.py`, `explain.py`, `service.py`, `core.py`
- Behaviour change: with a non-UTC `default_timezone`, date-only items move to
  00:00 UTC of their day, so `watch` sees them as changed once. `parsedate`
  output changes shape and exits with code 1 for text that is not a date.
- No new dependency; works with qddate 1.0.17 and with the unreleased qddate
  whose default filter honours sessions.
