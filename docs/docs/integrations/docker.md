---
title: "Docker"
description: "Run newsworker from the published image, with Docker or Compose"
---

# Docker

Every release publishes a multi-architecture image (`linux/amd64`,
`linux/arm64`) to the GitHub Container Registry, tagged with the version,
`MAJOR.MINOR` and `latest`:

```bash
docker run --rm -p 127.0.0.1:8787:8787 \
  -v newsworker-home:/home/newsworker/.newsworker ghcr.io/ivbeg/newsworker
```

The default command is the feed server on `0.0.0.0:8787` inside the container,
with a health check on `/health/live`. The image includes the `metrics` extra;
expose Prometheus metrics at `/metrics` with `-e NEWSWORKER_METRICS_ENABLED=true`.
Any other subcommand works as well:

```bash
docker run --rm ghcr.io/ivbeg/newsworker extract https://example.com/news -f rss
```

To build locally instead: `docker build -t newsworker .`

With Compose (persists config and caches in a named volume):

```bash
docker compose up
```

The Compose example binds to loopback on the host by default. Do not expose the
container port publicly without `NEWSWORKER_API_TOKENS` (or a
`NEWSWORKER_FEED_SIGNING_KEY` for reader links) and preferably
`NEWSWORKER_ALLOWED_HOSTS`. Publish through a TLS reverse proxy when remote
access is required. See [security](/guides/security).
