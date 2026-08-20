---
title: "Local feed server"
description: "Expose any page as a pollable RSS/Atom URL on localhost"
---

# Local feed server

`serve` turns any page URL into a feed **on demand over GET**. Because the feed
URLs are plain GET requests, you can paste them into an RSS reader.

```bash
newsworker serve --port 8787
```

Then subscribe (URL-encode the page URL):

```text
http://127.0.0.1:8787/feed?url=https%3A%2F%2Fexample.com%2Fnews&format=atom
```

The first request for a URL builds and caches a parsing spec; later requests
reuse the cached spec and serve cached page content until its TTL expires.

The server binds to `127.0.0.1` by default. If you expose it on a routable
interface, restrict `allowed_hosts`, configure API tokens, and place it behind
a reverse proxy. See [security](/guides/security) and
[feed server](/integrations/feed-server).
