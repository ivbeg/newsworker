---
title: "batch"
description: "newsworker batch command reference"
---

# `batch`

Extracts feeds from a list of pages concurrently, writing one file per URL.

```bash
newsworker batch [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--urls-file` | | — | Text file with one page URL per line. |
| `--from-opml` | | — | OPML file; each outline's `xmlUrl` feed is read and normalised. |
| `--opml-pages` | | `false` | Extract from each outline's `htmlUrl` page instead of its feed. |
| `--output-dir` | `-d` | `.` | Directory for one output file per URL. |
| `--format` | `-f` | `json` | Output format (same set as `extract`). |
| `--max-workers` | | `4` | Concurrent workers (thread pool, or aiohttp when `--async`). |
| `--async` | | `false` | Use the optional aiohttp transport (`newsworker[async]`). |
| `--manifest` | | — | Write a run manifest to this path. |
| `--manifest-format` | | `json` | Manifest format: `json` or `csv`. |
| `--failure-policy` | | `strict` | `strict` or `partial-success`. |
| `--no-cache` | | `false` | Bypass caches for this run. |
| `--config` | `-c` | *(default)* | Path to settings YAML. |
| `--verbose` | `-v` | `false` | Verbose logging. |

```bash
newsworker batch --urls-file urls.txt --output-dir out --format rss
newsworker batch --from-opml feeds.opml -d out -f json --max-workers 8
pip install 'newsworker[async]'
newsworker batch --urls-file urls.txt -d out --async
```

Both transports apply the same fetch policy, robots.txt rules, per-host pacing,
cookies (`cookies_file`) and content cache: a fresh cached page is not fetched
again and a stale one is revalidated with `If-None-Match` / `If-Modified-Since`.

See [batch manifests](/guides/batch) for artifact naming, record fields, and
exit codes.
