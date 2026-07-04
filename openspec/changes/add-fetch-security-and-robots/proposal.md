# Change: Respect robots.txt and secure TLS verification by default

## Why
Two fetch-time gaps remain. `FeedExtractor.fetch` still passes `verify=False`, disabling
TLS verification for every request (the audit's single highest-priority fix, D10). And the
fetcher ignores `robots.txt`, so it can crawl disallowed paths (E2). Both are small,
high-impact changes to fetching behavior.

## What Changes
- **BREAKING (secure default):** default HTTP fetches to `verify=True`; add an
  `--insecure` flag and `verify_tls` setting for explicit opt-out.
- Add `can_fetch(url, user_agent)` using `urllib.robotparser`; consult it before fetching
  and honor `Crawl-delay` where present.
- Add a `respect_robots` setting (default on) and a `--ignore-robots` CLI escape hatch.
- Be lenient when `robots.txt` cannot be retrieved (allow the fetch).

## Impact
- Affected specs: `feed-extraction`
- Affected code: `extractor.py` (`fetch`), `tools.py` (`can_fetch`), `settings.py`, `core.py`
- **BREAKING**: sites with broken certificate chains now fail unless `--insecure` is set.
