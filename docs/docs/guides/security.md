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
are blocked by default. The check runs twice: on the resolved addresses before
the request, and on the address the socket actually connected to, so a DNS
answer that changes in between (DNS rebinding) cannot reach an internal service.
Intranet crawling is an explicit opt-in and still requires a host allow-list.
Proxy-based remote DNS reduces local verification; enable `trusted_proxy` only
when that trade-off is intentional.

Credentials stay with the origin they were configured for. On a redirect to a
different scheme, host or port, `Authorization`, `Cookie`, `X-API-Key` and every
header from `extra_headers` / `--header` are dropped. Delivery channels
(webhooks, Telegram) never inherit the source `extra_headers`.

`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` and `.netrc` are ignored unless
`trust_env_proxy: true` is set; configure a proxy explicitly with `proxy` /
`--proxy` instead.

Crawled sites are paced per host across every worker in the process: at most
`per_host_concurrency` requests in flight (default 2), at least `per_host_delay`
seconds between request starts, raised to the site's robots.txt `Crawl-delay`
(capped at 60 s). A `429` or `503` with `Retry-After` pauses that host; a request
that would wait longer than `max_host_wait` fails fast with a `rate_limited`
error instead of holding a worker. robots.txt rules are fetched through the same
policy and cached for at most a day.

Item links and images are limited to `http`/`https`; `javascript:`, `data:` and
other schemes found on a page are dropped before any output is produced.

The stdlib server supports static bearer tokens (`Authorization: Bearer …`) and
`X-API-Key`, constant-time token comparison, per-client token buckets, a global
feed build semaphore, request IDs, explicit CORS origins, and separate
`/health/live` and `/health/ready` routes. `/health` remains a liveness alias.
HTML responses include a restrictive CSP and `X-Content-Type-Options: nosniff`;
the exported HTML preview carries the same policy in a `<meta>` tag.
`?refresh=1` bypasses the caches only for loopback clients or, when API tokens
are configured, for authenticated requests; other clients get the cached feed
and a `Warning` header, so the server cannot be used to hammer third-party sites.

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
