---
title: "extract"
description: "newsworker extract command reference"
---

# `extract`

Extracts news items from an HTML page and renders them in the chosen format.

```bash
newsworker extract URL [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--format` | `-f` | `json` | Output format: `json`, `jsonfeed`, `rss`, `atom`, `csv`, `html`, `markdown`, `yaml`. |
| `--output` | `-o` | *(stdout)* | Write the result to a file instead of printing it. |
| `--spec` | `-s` | — | Path to a YAML spec produced by `analyze`. |
| `--limit` | `-n` | — | Maximum number of items to emit. |
| `--max-pages` | | `1` | Follow up to N "next" links, merging items across pages. |
| `--since` | | — | Only items on or after this date (`YYYY-MM-DD`). |
| `--until` | | — | Only items on or before this date (`YYYY-MM-DD`). |
| `--full-text` | | `false` | Follow each item link and extract the article body into `content` (`newsworker[fulltext]`). |
| `--file` | | — | Local HTML file (`-` for stdin). Requires `--base-url`. |
| `--base-url` | | — | Absolute HTTP(S) URL used to resolve links in local HTML. |
| `--undated` | | `false` | Opt in to the undated listing fallback. |
| `--render` | | `false` | Force Playwright rendering (`newsworker[browser]`). |
| `--explain` / `--explain-json` | | `false` | Print extraction diagnostics. |
| `--user-agent` | | *(built-in)* | Override the User-Agent used for fetching. |
| `--language` | | *(auto)* | Override the auto-detected feed language (e.g. `en`, `fr`). |
| `--proxy` | | — | Proxy URL for outgoing requests. |
| `--timeout` | | `30` | HTTP request timeout in seconds. |
| `--header` | | — | Extra HTTP header `Key: Value` (repeatable). |
| `--cookies` | | — | Path to a Netscape/Mozilla cookie jar file. |
| `--insecure` | | `false` | Disable TLS certificate verification for this run. |
| `--ignore-robots` | | `false` | Fetch even when `robots.txt` disallows it. |
| `--json-logs` | | `false` | Emit logs as structured JSON. |
| `--no-cache` | | `false` | Bypass the spec and content caches for this run. |
| `--refresh` | | `false` | Force re-fetching the page, ignoring cached content. |
| `--config` | `-c` | *(default)* | Path to a settings YAML file. |
| `--verbose` | `-v` | `false` | Verbose logging. |

Examples:

```bash
newsworker extract "https://example.com/news"
newsworker extract "https://example.com/news" -f rss
newsworker extract "https://example.com/news" -f atom -o feed.xml
newsworker extract "https://example.com/news" -s example.yaml -f rss
newsworker extract --file archive/page.html --base-url https://example.com/news/ -f json
```

See [output formats](/guides/output-formats), [local input](/guides/local-input),
[undated listings](/guides/undated), and [diagnostics](/guides/diagnostics).
