# Change: Record capabilities delivered by the 2026 improvement roadmap

## Why
The 2026 improvement roadmap (stabilisation, reliability, accuracy and UX,
expansion) shipped behaviour that no spec describes yet: native feed
passthrough, structured-data extraction, connect-time address checks, per-host
politeness, signed feed links, chat delivery channels, multi-source watch, item
history, the `explain` command, the extraction corpus gate, the release
workflow and the MCP server. Recording it keeps the specs the source of truth
for the next release.

## What Changes
- **feed-extraction**: native RSS/Atom/JSON Feed passthrough; JSON-LD and
  microdata article lists; plausible-date validation; multilingual relative
  dates; empty-result exit code.
- **network-fetch-policy**: address validation at connection time; credential
  stripping on cross-origin redirects; per-host pacing honouring
  `Crawl-delay` and `Retry-After`; proxy environment opt-in.
- **feed-server**: HMAC-signed feed links and public subscription URLs.
- **delivery-channels**: Slack, Discord and Matrix channels.
- **watch-delivery-reliability**: watching many sources; item history and
  opt-in update notifications.
- **extraction-diagnostics**: the `explain` report.
- **quality-gates**: the labelled extraction corpus gate and network smoke check.
- **deployment**: tagged release workflow with container image.
- **mcp-server** (new capability): Model Context Protocol tools.

## Impact
- Affected specs: feed-extraction, network-fetch-policy, feed-server,
  delivery-channels, watch-delivery-reliability, extraction-diagnostics,
  quality-gates, deployment, mcp-server (new).
- Affected code: already implemented on the roadmap branches (`native.py`,
  `structured.py`, `dates.py`, `relative.py`, `fetch.py`, `server.py`,
  `delivery.py`, `watching.py`, `dedup.py`, `explain.py`, `evaluation.py`,
  `mcp_server.py`, `.github/workflows/release.yml`). No new code in this change.
