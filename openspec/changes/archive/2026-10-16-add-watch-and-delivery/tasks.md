## 1. Pagination
- [x] 1.1 Detect a "next" link in `SpecExtractor`/dynamic path (`tools.find_next_link`)
- [x] 1.2 Follow pages up to `--max-pages`, merging items (respect robots + rate limits)

## 2. Deduplication
- [x] 2.1 Add a SQLite-backed store of seen `unique_id` hashes (path in settings)
- [x] 2.2 On each run, filter out previously seen items and record them

## 3. Webhook delivery
- [x] 3.1 Add a webhook client POSTing new items as JSON with retry/backoff
- [x] 3.2 Add `--webhook URL` option; validate the target URL

## 4. Watch mode
- [x] 4.1 Add `watch URL --interval N [--webhook ...] [--max-pages ...]`
- [x] 4.2 Loop on the interval; emit/deliver only new items; exit cleanly on SIGINT/SIGTERM

## 5. Tests & docs
- [x] 5.1 Test pagination merge and `--max-pages` bound
- [x] 5.2 Test dedup store filters seen items across runs
- [x] 5.3 Test webhook payload and retry (mocked); document watch mode in README
