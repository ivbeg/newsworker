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

## Impact
- Affected specs: `language-support`, `feed-extraction`, `extraction-diagnostics`
- Affected code: `dates.py`, `runtime.py`, `extractor.py`, `spec/execute.py`,
  `tools.py`, `explain.py`
- No new dependency; works with qddate 1.0.17 and with the unreleased qddate
  whose default filter honours sessions.
