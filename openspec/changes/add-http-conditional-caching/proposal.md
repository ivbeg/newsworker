# Change: HTTP conditional caching, upstream revalidation, metrics, and cache write safety

## Why
`ThreadingHTTPServer` combined with the file cache races on concurrent writes to the same
key, the server never emits `ETag`/`Last-Modified` (so readers re-download unchanged
feeds), it never revalidates upstream pages conditionally, and there is no metrics
endpoint. These are correctness and efficiency gaps for the served path. (Audit C5, C6,
C8, C9.)

## What Changes
- Emit `ETag` (hash of the rendered body) and `Last-Modified` on `/feed`; honor
  `If-None-Match`/`If-Modified-Since` with `304 Not Modified`.
- Store upstream `ETag`/`Last-Modified` in `ContentCache` metadata and send
  `If-Modified-Since`/`If-None-Match` on re-fetch, treating `304` as a cache hit.
- Make concurrent cache writes safe (per-key `threading.Lock` plus atomic
  write-and-rename).
- Add an optional Prometheus `/metrics` endpoint (request counter + extraction-latency
  histogram) that degrades gracefully when `prometheus_client` is absent.

## Impact
- Affected specs: `feed-server`
- Affected code: `server.py`, `cache.py` (metadata + locking + atomic rename),
  `service.py`/`extractor.py` (conditional upstream fetch), `settings.py`
