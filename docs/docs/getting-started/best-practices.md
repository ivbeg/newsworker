---
title: "Best practices"
description: "Recommended newsworker workflows for repeatable, safe extraction"
---

# Best practices

## Prefer native feeds when they exist

Run `scan` first. If the site already publishes RSS, Atom, or JSON Feed, import
that rather than reconstructing items from HTML.

## Analyze layouts you will crawl again

Generate a spec once and reuse it. Specs are faster, deterministic, and easier
to review than repeating the heuristic pipeline. Store them in version control
or as [site bridges](/integrations/plugins-and-bridges).

## Keep fetch policy conservative

Leave TLS verification and `robots.txt` compliance on. Bind `serve` to loopback
unless you have tokens, an allow-list, and a reverse proxy. See
[security](/guides/security).

## Use local archives for tests

`extract --file` / `analyze --file` with `--base-url` keeps fixtures offline and
reproducible. See [local input](/guides/local-input).

## Inspect before automating

Use `--explain` or `--explain-json` when a layout changes. Treat confidence
scores as a review aid, not a correctness probability.

## Deliver new items through watch, not cron-plus-extract

`watch` tracks seen items, retries failed deliveries, and supports stdout,
webhook, SMTP, and Telegram channels. See [delivery](/guides/delivery).

## Measure before raising concurrency

Default browser concurrency is one for a reason. Batch `--max-workers` and
`--async` should be sized against the target site's robots and rate limits.
