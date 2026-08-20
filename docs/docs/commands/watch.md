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
| `--format` | `-f` | `json` | Output format when using stdout. |
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

See [delivery](/guides/delivery) for outbox guarantees and channel credentials.
