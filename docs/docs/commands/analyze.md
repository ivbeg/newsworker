---
title: "analyze"
description: "newsworker analyze command reference"
---

# `analyze`

Runs the dynamic heuristics once and distils them into a portable YAML parsing
spec. Feeding that spec back into `extract --spec` skips analysis and runs
deterministic selectors.

```bash
newsworker analyze URL [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--output` | `-o` | *(stdout)* | Path to write the YAML spec. |
| `--file` | | — | Local HTML file (`-` for stdin). Requires `--base-url`. |
| `--base-url` | | — | Absolute HTTP(S) URL used to resolve links in local HTML. |
| `--user-agent` | | *(built-in)* | Override the User-Agent used for fetching. |
| `--language` | | *(auto)* | Override the auto-detected feed language. |
| `--proxy` | | — | Proxy URL for outgoing requests. |
| `--timeout` | | `30` | HTTP request timeout in seconds. |
| `--header` | | — | Extra HTTP header `Key: Value` (repeatable). |
| `--cookies` | | — | Path to a Netscape/Mozilla cookie jar file. |
| `--insecure` | | `false` | Disable TLS certificate verification. |
| `--ignore-robots` | | `false` | Fetch even when `robots.txt` disallows it. |
| `--json-logs` | | `false` | Emit logs as structured JSON. |
| `--config` | `-c` | *(default)* | Path to a settings YAML file. |
| `--verbose` | `-v` | `false` | Verbose logging. |

`analyze` uses the same fetch settings as `extract`. It records what the dynamic
extractor would choose — including `<time datetime="...">` dates and
heading-based titles — and fails with a clear error when no dated news listings
are found.

```bash
newsworker analyze "https://example.com/news" -o example.yaml
newsworker extract "https://example.com/news" -s example.yaml -f rss
```

See [parsing specs](/guides/parsing-specs) for the YAML format, field reference,
and analysis pipeline.
