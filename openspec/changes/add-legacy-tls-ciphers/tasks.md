## 1. Policy and settings
- [x] 1.1 Add `legacy_tls_ciphers` to `Settings`, `FetchPolicy` and `policy_from_settings`
- [x] 1.2 Carry it through `FeedExtractor`, `FeedService`, `FeedsFinder` and the CLI extractor
- [x] 1.3 Document the setting in `settings_doc.py` and regenerate the reference

## 2. Transports
- [x] 2.1 Requests: shared legacy TLS context added to the pool key when the active policy opts in
- [x] 2.2 aiohttp: `_ssl_context` sets the legacy cipher list when asked
- [x] 2.3 Append the hint to handshake-failure errors when the option is off

## 3. CLI
- [x] 3.1 `--legacy-tls-ciphers` on `analyze` and `extract`

## 4. Tests and docs
- [x] 4.1 Local HTTPS server limited to `AES256-GCM-SHA384`: fails without the option, succeeds with it
- [x] 4.2 Unit tests for contexts, hint, settings plumbing and the CLI flag
- [x] 4.3 README, command pages, troubleshooting, settings guide and CHANGELOG
