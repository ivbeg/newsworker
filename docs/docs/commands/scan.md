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
| `--max-workers` | | `8` | Candidate feeds verified at the same time. |
| `--output` | `-o` | *(stdout)* | Write the result to a file. |
| `--fail-on-empty` | | `false` | Exit with status `3` when no feeds are found. An unreachable page always exits with `1`. |
| `--ignore-robots` | | `false` | Fetch even when `robots.txt` disallows it. |
| `--crawl` | | `false` | Also follow same-site links and look for feeds on those pages. |
| `--max-pages` | | `50` | Pages a crawl fetches at most. Needs `--crawl`. |
| `--max-depth` | | `2` | Link steps a crawl goes from the URL. Needs `--crawl`. |
| `--listings` | | `false` | Also report pages that extraction reads as dated news listings (`feedtype: html`). |
| `--config` | `-c` | *(default)* | Settings YAML file. |
| `--verbose` | `-v` | `false` | Verbose logging. |

```bash
newsworker scan "https://www.dta.gov.au/news/"
newsworker scan "https://www.dta.gov.au/news/" -f opml -o feeds.opml
newsworker scan "https://example.com" --sitemap --format json
newsworker scan "https://example.com" --crawl --listings
newsworker scan "https://example.com" --crawl --max-pages 20 -f csv
```

`scan` verifies every candidate feed by parsing it unless `--no-verify` is set.
`feedtype`, `num_entries`, and `language` metadata are included where available.

With `--crawl`, each candidate lists the pages it was found on (`found_on`,
`found_on_count`) and the JSON result has a `crawl` summary; CSV gets a last
`found_on` column. `--max-pages` and `--max-depth` without `--crawl` exit with
status `2`. See [crawling a site](/guides/discovery#crawling-a-site).

See [discovery](/guides/discovery) and [output formats](/guides/output-formats).
