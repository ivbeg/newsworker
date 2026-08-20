---
title: "CLI Reference"
description: "Index of newsworker CLI commands"
slug: /commands
---

# CLI Reference

All commands are available as `newsworker <command>`. Use `newsworker --help`
for the live flag list, and `newsworker <command> --help` for per-command
options. Add `--verbose` / `-v` to any command for detailed execution logs.

| Command | Page |
|---------|------|
| `extract` | [`/commands/extract`](/commands/extract) |
| `serve` | [`/commands/serve`](/commands/serve) |
| `scan` | [`/commands/scan`](/commands/scan) |
| `analyze` | [`/commands/analyze`](/commands/analyze) |
| `batch` | [`/commands/batch`](/commands/batch) |
| `watch` | [`/commands/watch`](/commands/watch) |
| `cache` | [`/commands/cache`](/commands/cache) |
| `spec` | [`/commands/spec`](/commands/spec) |
| `parsedate` | [`/commands/parsedate`](/commands/parsedate) |

Shared fetch flags (`--user-agent`, `--proxy`, `--timeout`, `--header`,
`--cookies`, `--insecure`, `--ignore-robots`, `--language`, `--config`) appear
on `extract` and `analyze`. Settings resolution is documented in
[runtime configuration](/guides/runtime-configuration).
