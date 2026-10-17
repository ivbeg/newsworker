# Change: Add opt-in legacy TLS ciphers

## Why
Some public sites (for example `https://minfin.am/en/page/news/`) accept only
TLS 1.2 suites with static RSA key exchange, such as `AES256-GCM-SHA384`.
Python 3.10+ and urllib3 2 no longer offer those suites, so every fetch fails
with `SSLV3_ALERT_HANDSHAKE_FAILURE`, and `--insecure` does not help because the
certificate is fine. Users have no way to read such sites.

## What Changes
- New setting `legacy_tls_ciphers` (default `false`, env
  `NEWSWORKER_LEGACY_TLS_CIPHERS`) and `FetchPolicy.legacy_tls_ciphers`.
- When enabled, the requests and aiohttp transports use OpenSSL's `DEFAULT`
  cipher list, which adds the static-RSA suites. Certificate and host-name
  checks and OpenSSL security level 2 stay in force. The requests transport
  keys the legacy TLS context into its own connection pools.
- `--legacy-tls-ciphers` flag on `analyze` and `extract`.
- A TLS handshake failure while the option is off ends with a hint that names
  the flag and the setting.
- Minimum `requests` raised to 2.32.2 for `build_connection_pool_key_attributes`.

## Impact
- Affected specs: `network-fetch-policy`
- Affected code: `fetch.py`, `async_fetch.py`, `settings.py`, `settings_doc.py`,
  `core.py`, `extractor.py`, `service.py`, `finder.py`, `pyproject.toml`
- Security: opt-in only; enabling it gives up forward secrecy for servers that
  choose those suites, never certificate verification.
