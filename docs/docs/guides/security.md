---
title: "Security"
description: "Shared fetch policy, SSRF guards, server access controls, and browser sandboxing"
---

# Network and server security

All source, discovery, sitemap, pagination, full-text, asynchronous, browser
navigation, and delivery HTTP operations use the shared fetch-policy contract.
It validates the scheme and host, resolves and classifies every IPv4/IPv6
destination, validates each redirect hop, applies TLS/timeout/size/redirect
limits, and returns requested and effective URLs with response metadata. Parsers
receive bounded bytes and never fetch a candidate URL themselves.

Loopback, private, link-local, multicast, unspecified, and reserved addresses
are blocked by default. Intranet crawling is an explicit opt-in and still
requires a host allow-list. Proxy-based remote DNS reduces local verification;
enable `trusted_proxy` only when that trade-off is intentional.

The stdlib server supports static bearer tokens (`Authorization: Bearer …`) and
`X-API-Key`, constant-time token comparison, per-client token buckets, a global
feed build semaphore, request IDs, explicit CORS origins, and separate
`/health/live` and `/health/ready` routes. `/health` remains a liveness alias.
HTML responses include a restrictive CSP and `X-Content-Type-Options: nosniff`.

Do not expose the container port publicly without configuring
`NEWSWORKER_API_TOKENS` and preferably an outbound `NEWSWORKER_ALLOWED_HOSTS`
list. The Compose example binds to loopback by default; publish it through a
TLS reverse proxy when remote access is required.

Browser rendering executes untrusted JavaScript. Use it only in a container or
process sandbox with an outbound firewall. Newsworker limits browser
concurrency, navigation time, rendered bytes, redirects, and unnecessary
media/font resources, but browser subresource policy is necessarily
best-effort.

See [runtime configuration](/guides/runtime-configuration) and
[browser rendering](/guides/browser-rendering).
