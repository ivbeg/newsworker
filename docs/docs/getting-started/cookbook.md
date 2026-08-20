---
title: "Cookbook"
description: "Pick a role and goal, then follow verified newsworker commands"
---

# Cookbook

newsworker covers several workflows. This page is a task-oriented index: find the
row that sounds like you, then follow the linked reference. If you are completely
new, do the [quick start](/getting-started/quick-start) first.

| You are a… | You want to… | Start with |
|------------|--------------|------------|
| [Feed subscriber](/use-cases/html-to-feed) | Turn a news listing into RSS/Atom for a reader | `extract`, `serve` |
| [Open-data / OSINT researcher](/use-cases/feed-discovery) | Find feeds a site already publishes | `scan` |
| [Site operator](/use-cases/parsing-specs) | Crawl the same layout quickly and repeatably | `analyze`, `extract --spec`, site bridges |
| [Automation builder](/use-cases/watch-and-delivery) | Poll a page and deliver only new items | `watch`, webhooks, SMTP, Telegram |
| [Pipeline author](/use-cases/batch-pipelines) | Extract many pages with a stable manifest | `batch` |
| [Application developer](/integrations/python-library) | Embed extraction in Python | `FeedService`, `format_feed` |
| [Operator](/integrations/docker) | Run the feed server in a container | Docker / Compose, [security](/guides/security) |

## Detailed walkthroughs

- [HTML to feed](/use-cases/html-to-feed)
- [Feed discovery](/use-cases/feed-discovery)
- [Local feed server](/use-cases/local-feed-server)
- [Watch and delivery](/use-cases/watch-and-delivery)
- [Batch pipelines](/use-cases/batch-pipelines)
- [Parsing specs](/use-cases/parsing-specs)
