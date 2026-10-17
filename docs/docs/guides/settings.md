---
title: "Settings and caching"
description: "YAML settings file, spec/content caches, and default cache behaviour"
---

# Settings and caching

Both `extract` and `serve` share a small caching layer that avoids redundant
work:

- **Spec cache** — the parsing spec for a URL is built dynamically on first use
  and stored as YAML. Subsequent runs reuse it (fast, deterministic).
- **Content cache** — the fetched page bytes are stored with a configurable
  time-to-live, so a page is not re-downloaded on every request while it is
  still fresh.

Settings are read from a YAML file, by default `~/.newsworker/config.yaml`
(created with defaults on first run). Point to a different file with
`--config` / `-c`. Environment variables and CLI flags override file values;
see [runtime configuration](/guides/runtime-configuration). The example below
shows the common settings; the [settings reference](/guides/settings-reference)
lists every one with its default and environment variable.

```yaml
cache_dir: ~/.newsworker/cache   # where cached specs and page content live
content_ttl: 3600                # seconds a cached page stays fresh
spec_ttl: 0                      # seconds a cached spec is valid (0 = never expires)
host: 127.0.0.1                  # local server bind interface
port: 8787                       # local server port
filtered_text_length: 150        # max text length considered for date detection
max_content_bytes: 10485760      # cap on fetched response size (bytes)
allowed_hosts: []                # feed-server host allow-list ([] = any host)
content_cache_max_entries: 0     # max cached pages on disk (0 = unbounded)
content_cache_max_bytes: 0       # max total cached-page size on disk (0 = unbounded)
spec_cache_max_entries: 0        # max cached specs on disk (0 = unbounded)
verify_tls: true                 # verify TLS certificates on outgoing requests
legacy_tls_ciphers: false        # also offer TLS 1.2 ciphers without forward secrecy
respect_robots: true             # honor robots.txt (incl. Crawl-delay) before fetching
per_host_concurrency: 2          # requests in flight per site, across all workers (0 = unlimited)
per_host_delay: 0                # minimum seconds between requests to one site
max_host_wait: 30                # longest wait for a slot or a Retry-After window (seconds)
request_timeout: 30              # HTTP request timeout (seconds)
proxy: ""                        # proxy URL for outgoing requests ("" = none)
extra_headers: {}                # extra HTTP headers sent with every request
cookies_file: ""                 # optional Netscape/Mozilla cookie jar path
default_language: ""             # feed language override ("" = auto-detect)
bridges_dir: ""                  # user site-bridge YAML dir ("" = ~/.newsworker/bridges)
use_async: false                 # use aiohttp for batch --async (needs [async] extra)
full_text: false                 # follow item links and populate content (needs [fulltext])
full_text_workers: 4             # concurrency for --full-text fetches
structured_data: true            # use JSON-LD / microdata article lists when present
native_feeds: true               # read RSS/Atom/JSON Feed responses as feeds
trust_env_proxy: false           # honor HTTP(S)_PROXY / NO_PROXY / .netrc
history_retention_days: 365      # item history kept by watch (0 = forever)
```

Cached specs live under `<cache_dir>/specs/` and cached page content under
`<cache_dir>/content/`, keyed by a hash of the source URL. Use `--no-cache`
(bypass caches) or `--refresh` / `?refresh=1` (force a re-fetch) to override the
caches for a single run/request.

Inspect caches with [`cache`](/commands/cache).
