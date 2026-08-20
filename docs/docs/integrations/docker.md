---
title: "Docker"
description: "Run the newsworker feed server with Docker or Compose"
---

# Docker

Run the feed server in a container (binds to `0.0.0.0:8787` inside the image):

```bash
docker build -t newsworker .
docker run --rm -p 8787:8787 -v newsworker-home:/home/newsworker/.newsworker newsworker
```

Or with Compose (persists config/cache in a named volume):

```bash
docker compose up
```

The Compose example binds to loopback on the host by default. Do not expose the
container port publicly without `NEWSWORKER_API_TOKENS` and preferably
`NEWSWORKER_ALLOWED_HOSTS`. Publish through a TLS reverse proxy when remote
access is required. See [security](/guides/security).
