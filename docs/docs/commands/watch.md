---
title: "watch"
description: "newsworker watch command reference"
---

# `watch`

Polls a page on an interval, tracks which items it has already seen (in a SQLite
store under the cache dir), and emits or delivers only new items.

```bash
newsworker watch URL [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--interval` | `-i` | `300` | Seconds between polls. |
| `--channel` | | `stdout` | Repeatable destination: `stdout`, `webhook`, `smtp`, `telegram`. |
| `--webhook` | | — | POST new items as JSON to this URL (with retry/backoff). |
| `--smtp-recipient` | | — | SMTP recipient when `--channel smtp`. |
| `--telegram-chat-id` | | — | Telegram chat id when `--channel telegram`. |
| `--format` | `-f` | `json` | Stdout output: `json` writes one JSON object per line (JSON Lines); `rss`, `atom`, `jsonfeed`, `csv`, `html`, `markdown` and `yaml` write one document per poll with that poll's new items. |
| `--max-pages` | | `1` | Pages to follow per poll (pagination). |
| `--max-iterations` | | `0` | Stop after N polls (`0` = run until interrupted). |
| `--config` | `-c` | *(default)* | Path to settings YAML. |
| `--verbose` | `-v` | `false` | Verbose logging. |

```bash
newsworker watch "https://example.com/news" --interval 300
newsworker watch "https://example.com/news" --channel webhook \
  --webhook https://hooks.example/new --max-pages 3
```

The loop shuts down cleanly on Ctrl-C / SIGTERM. Use `--max-iterations N` to
stop after N polls (handy for cron-style single runs).

Each poll first retries deliveries that are due from earlier polls, then fetches
the page. A temporarily unavailable source therefore does not hold back items
that were already discovered. For finite runs (`--max-iterations N`) the exit
status is `1` when the last poll could not fetch the page or left deliveries
pending or failed, so cron and CI jobs can alert on it. Delivered history older
than `delivered_retention_days` is pruned after every poll.

See [delivery](/guides/delivery) for outbox guarantees and channel credentials.
