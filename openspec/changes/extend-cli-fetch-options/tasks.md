## 1. Item slicing/filtering (no network)
- [x] 1.1 Add `--limit/-n`, `--since`, `--until` to `extract`
- [x] 1.2 Parse ISO dates; filter `items` by `pubdate` then apply limit before formatting
- [x] 1.3 Handle items with missing `pubdate` (exclude from date filters, keep for limit)

## 2. Request options plumbing
- [x] 2.1 Add `timeout`, `proxy`, `headers`, `cookies_file` fields to `Settings`
- [x] 2.2 Extend `FeedExtractor.fetch` to accept timeout/proxy/headers/cookies
- [x] 2.3 Add `--user-agent`, `--proxy`, `--timeout`, `--header` (repeatable), `--cookies` to CLI
- [x] 2.4 Keep `validate_url` SSRF guard before every fetch

## 3. Meta options
- [x] 3.1 Add `@app.callback()` with `--version` printing `newsworker.__version__`
- [x] 3.2 Add `--json-logs` switching the log formatter to JSON

## 4. Tests & docs
- [x] 4.1 Unit test limit/since/until filtering on a fixture feed
- [x] 4.2 Unit test header/cookie/proxy plumbing (mock the session)
- [x] 4.3 Document new flags in README
