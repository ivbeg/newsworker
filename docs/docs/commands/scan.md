---
title: "scan"
description: "newsworker scan command reference"
---

# `scan`

Scans a page for already-published RSS/Atom/JSON Feed declarations (via
autodiscovery links, feed icons, link heuristics, WebSub, and optional sitemaps)
and reports them.

```bash
newsworker scan URL [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--format` | `-f` | `json` | Output format: `json`, `rss`, `atom`, `csv`, `opml`. |
| `--sitemap` | | `false` | Also discover feed URLs from the site's `/sitemap.xml`. |
| `--no-verify` | | `false` | Skip fetching and parsing candidate feeds. |
| `--output` | `-o` | *(stdout)* | Write the result to a file. |
| `--verbose` | `-v` | `false` | Verbose logging. |

```bash
newsworker scan "https://www.dta.gov.au/news/"
newsworker scan "https://www.dta.gov.au/news/" -f opml -o feeds.opml
newsworker scan "https://example.com" --sitemap --format json
```

`scan` verifies every candidate feed by parsing it unless `--no-verify` is set.
`feedtype`, `num_entries`, and `language` metadata are included where available.

See [discovery](/guides/discovery) and [output formats](/guides/output-formats).
