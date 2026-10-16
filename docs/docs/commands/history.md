---
title: "history"
description: "newsworker history command reference"
---

# `history`

`watch` records every item it sees in its SQLite store: when it first and last
appeared, and a new version each time its title, text, link or date changes.
`history` exports that record.

```bash
newsworker history [URL] [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--format` | `-f` | `jsonl` | `jsonl` (one JSON object per line) or `csv`. |
| `--since` | | — | Only items first seen on or after this date (`YYYY-MM-DD`). |
| `--output` | `-o` | *(stdout)* | Write to a file. |
| `--config` | `-c` | *(default)* | Settings YAML (the store lives in the cache directory). |

Columns: `feed`, `uid`, `version`, `title`, `link`, `pubdate`, `first_seen`,
`last_seen` (UTC, ISO 8601). Entries not seen for `history_retention_days`
(default 365, `0` keeps everything) are pruned while `watch` runs.

To be notified about edits, run `watch --deliver-updates`: a changed item is
delivered again, once per version, with `updated: true` (chat channels prefix
the title with "Updated:").
