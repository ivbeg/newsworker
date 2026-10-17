---
title: "serve"
description: "newsworker serve command reference"
---

# `serve`

Runs a lightweight local HTTP server (Python standard library, no extra
dependencies) that turns any page URL into a feed on demand over GET.

```bash
newsworker serve [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--host` | `-h` | `127.0.0.1` | Interface to bind. |
| `--port` | `-p` | `8787` | Port to listen on. |
| `--config` | `-c` | *(default)* | Path to a settings YAML file. |
| `--cache-dir` | | *(settings)* | Directory for cached specs and page content. |
| `--content-ttl` | | *(settings)* | Seconds a cached page stays fresh. |
| `--verbose` | `-v` | `false` | Verbose logging. |

## Endpoints

| Route | Description |
| --- | --- |
| `GET /feed?url=<page>&format=atom` | Build a feed from `<page>`. Add `&refresh=1` to bypass caches. Responses include `ETag` / `Last-Modified`. |
| `GET /health` | Liveness alias. |
| `GET /health/live` | Liveness. |
| `GET /health/ready` | Readiness. |
| `GET /metrics` | Prometheus metrics when `newsworker[metrics]` is installed; otherwise `404`. |
| `GET /` | In a browser: a form to paste a news page URL, preview its items and copy the feed link. Other clients get short usage help. |

`format` is one of `atom` (default), `rss`, `json`, `jsonfeed`, `csv`, `html`,
`markdown`, `yaml`. Server clients may opt into bounded confidence and warning
headers with `diagnostics=1`.

```bash
newsworker serve --port 8787
```

```text
http://127.0.0.1:8787/feed?url=https%3A%2F%2Fexample.com%2Fnews&format=atom
```

## Home page

Open `http://127.0.0.1:8787/` in a browser, paste a news page URL and choose a
format: the page lists the items newsworker finds and shows the link to add to
a feed reader. It runs no script and posts only to itself.

On a protected server the form follows the same rules as `/feed`: with
`api_tokens` the request must carry a token, and with only a
`feed_signing_key` signed links are shown to clients on the same machine (the
operator), so visitors cannot mint links for arbitrary pages. Everyone else sees
a note to ask the operator for a link (`newsworker feed-url`).

:::caution Security
The server fetches whatever URL is passed to `/feed?url=`, so it is a
server-side request forgery (SSRF) surface. Bind to loopback by default. If you
expose it, set `allowed_hosts` and API tokens. See [security](/guides/security).
:::

See [feed server](/integrations/feed-server).
