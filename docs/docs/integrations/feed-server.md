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

## Subscribing from a feed reader

Feed readers cannot send an `Authorization` header, so a server protected by
`api_tokens` would be unusable from them. Configure a signing key and hand out
signed links instead:

```yaml
public_base_url: https://feeds.example.org   # how readers reach the server
feed_signing_key: <a random string of 16+ characters>
```

```bash
newsworker feed-url "https://example.com/news" --format rss
# https://feeds.example.org/feed?url=https%3A%2F%2Fexample.com%2Fnews&format=rss&sig=…
```

A signature authorises exactly one source page and format; changing either
returns `401`. Signed links never force `?refresh=1`. With a signing key set,
`/feed` requires a valid signature or API token even when no tokens are
configured; `/metrics` still follows `api_tokens`. Rotating the key invalidates
every link handed out with it. The feed's `rel="self"` link is the signed URL,
so readers that follow it keep working.

For Docker deployment see [Docker](/integrations/docker). For fetch and bind
policy see [security](/guides/security).
