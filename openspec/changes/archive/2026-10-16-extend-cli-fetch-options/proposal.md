# Change: Extend CLI with common fetch and output options

## Why
The Typer CLI is clean but bare. Power users expect standard feed-fetching flags that are
each a small change to `core.py` plus light plumbing into `service.py`/`extractor.py`.
(Audit B1–B8, B12.)

## What Changes
- `--limit N` / `-n`: cap the number of emitted items (slice before formatting).
- `--since` / `--until`: filter items by `pubdate` (ISO `YYYY-MM-DD`).
- `--user-agent STRING`: override the hardcoded User-Agent (already threaded into
  `extractor.fetch`; expose it and persist via `Settings`).
- `--proxy URL`: pass through to the requests session (`proxies=`).
- `--timeout SECONDS`: expose the currently hardcoded 30s timeout as a flag + setting.
- `--header "Key: Value"`: repeatable custom HTTP headers.
- `--cookies FILE`: load a Netscape cookie jar (`http.cookiejar.MozillaCookieJar`).
- `--version`: print `__version__` via an `@app.callback()`.
- `--json-logs`: emit structured JSON logs for cron/deployment use.
- Apply fetch options to `extract` (and, where sensible, `scan`).

## Impact
- Affected specs: `cli`
- Affected code: `core.py`, `service.py`, `extractor.py` (`fetch`), `settings.py`
- Note: `--user-agent`, `--proxy`, `--timeout`, `--header`, `--cookies` change how outgoing
  requests are made; keep the SSRF guard (`validate_url`) intact.
