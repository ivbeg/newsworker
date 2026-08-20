---
title: "Feed server"
description: "Local HTTP server endpoints, caching, and access controls"
---

# Feed server

`newsworker serve` is a stdlib HTTP server with no extra dependencies. Feed URLs
are plain GET requests, so RSS readers can poll them directly.

See [`serve`](/commands/serve) for flags and routes. Conditional GET (`ETag` /
`304`) is supported. Optional Prometheus metrics require `newsworker[metrics]`.

Access controls include static bearer tokens, API keys, per-client rate limits,
a global feed-build semaphore, request IDs, and explicit CORS origins. HTML
responses include a restrictive CSP.

For Docker deployment see [Docker](/integrations/docker). For fetch and bind
policy see [security](/guides/security).
