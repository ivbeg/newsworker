---
title: "Output formats"
description: "JSON, JSON Feed, RSS, Atom, CSV, HTML, Markdown, YAML, and OPML outputs"
---

# Output formats

## `extract`

| Format | Description |
| --- | --- |
| `json` | The raw internal representation (feed metadata + items). Default. |
| `jsonfeed` | [JSON Feed 1.1](https://jsonfeed.org/version/1.1) document. |
| `rss` | RSS 2.0 document generated with [`feedgen`](https://github.com/lkiesow/python-feedgen). |
| `atom` | Atom 1.0 document generated with `feedgen`. |
| `csv` | Flat table of items: `title, link, pubdate, description, image, unique_id`. |
| `html` | A standalone HTML preview page rendering items as cards. |
| `markdown` | A Markdown bulleted list (date, title, link per item). |
| `yaml` | The feed dictionary serialized as YAML (symmetric with the spec format). |

## `scan`

| Format | Description |
| --- | --- |
| `json` | The raw list of discovered feeds. Default. |
| `rss` / `atom` | Each discovered feed becomes an entry (its title and URL). |
| `csv` | Flat table: `title, url, feedtype, num_entries, language, confidence`. |
| `opml` | OPML 2.0 subscription list for importing feeds into readers. |

Publication times in the internal feed dictionary are timezone-aware UTC
`datetime` values. When rendering RSS/Atom they are emitted as UTC (a
requirement of the feed formats). See [migration notes](/guides/migration-1-4)
for `content_kind` and enclosure rules.

Undated items keep null/empty date fields where the target format permits them
and are not fabricated. See [undated listings](/guides/undated).
