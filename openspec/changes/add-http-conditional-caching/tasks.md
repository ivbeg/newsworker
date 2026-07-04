## 1. Cache write safety
- [x] 1.1 Add a per-key lock registry to the caches
- [x] 1.2 Write to a temp file and `os.replace` (atomic rename) on `set`
- [x] 1.3 Regression test: concurrent writers to one key never corrupt the entry

## 2. Downstream conditional responses
- [x] 2.1 Compute a strong `ETag` from the rendered feed body; send `ETag` + `Last-Modified`
- [x] 2.2 Honor `If-None-Match`/`If-Modified-Since`; return `304` when unchanged

## 3. Upstream revalidation
- [x] 3.1 Persist upstream `ETag`/`Last-Modified` alongside cached content
- [x] 3.2 Send `If-Modified-Since`/`If-None-Match` on re-fetch; treat `304` as a fresh hit

## 4. Metrics
- [x] 4.1 Add optional `/metrics` (request counter, extraction latency histogram)
- [x] 4.2 Degrade gracefully (disable endpoint) when `prometheus_client` is not installed

## 5. Tests
- [x] 5.1 Test `304` responses for matching `If-None-Match`
- [x] 5.2 Test upstream `304` handling reuses cached content
