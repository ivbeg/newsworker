---
title: "feed-url"
description: "newsworker feed-url command reference"
---

# `feed-url`

Prints the feed-server URL a reader subscribes to for a page. When
`feed_signing_key` is configured the URL carries a signature, so readers that
cannot send an API token can still use a protected server.

```bash
newsworker feed-url URL [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--format` | `-f` | `atom` | Feed format the server returns (any `extract` format). |
| `--config` | `-c` | *(default)* | Settings YAML with `public_base_url` and `feed_signing_key`. |

```bash
newsworker feed-url "https://example.com/news" -f rss
```

See [feed server](/integrations/feed-server) for how signatures are checked.
