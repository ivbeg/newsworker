---
title: "How it works"
description: "How newsworker finds dated news listings and reconstructs feed items"
---

# How it works

Most news pages carry a **publication date** next to each item — `2017-09-27`,
`1 jul 2016`, `18/06/2018`, and hundreds of other variants. newsworker:

1. **Finds every date** on the page using [qddate](https://github.com/ivbeg/qddate),
   a fast pattern-based date parser that recognizes 340+ date formats across many
   languages, plus HTML `<time datetime="...">` attributes.
2. **Clusters** repeated, similarly-structured date nodes to tell apart a *page*
   date (footer, "last updated") from the *news list* area.
3. **Reconstructs each news item** around its date node, pulling out the title,
   description, link, and image.

The result is a structured feed you can serialize into JSON, JSON Feed, RSS, Atom,
CSV, HTML, Markdown, YAML, or OPML.

## When to use newsworker

Use newsworker when a site publishes fresh news **but offers no RSS/Atom feed**,
and when generic "page change" monitors are too noisy to be useful.

Prefer a native feed when `scan` finds one. Use `extract` as the fallback. Use
`analyze` when you will crawl the same layout repeatedly. Use `watch` when you
need only new items delivered to a webhook, SMTP, or Telegram channel.

## What it is not

- A general-purpose HTML scraper or CSS selector toolkit.
- A JavaScript-heavy SPA crawler by default. Optional Playwright rendering is
  available; see [browser rendering](/guides/browser-rendering).
- A guarantee that every language-specific date format is recognized. See
  [language support](/guides/language-support).

## Limitations

- Right-aligned dates such as `Published - 27-01-2018` are intentionally
  unsupported — supporting them measurably increases false positives.
- Pages that expose no dates in item text or URLs need the opt-in
  [undated listing fallback](/guides/undated).
- Browser rendering executes untrusted JavaScript and should run in a sandbox.

## Next steps

- [Quick start](/getting-started/quick-start)
- [Parsing specs](/guides/parsing-specs)
- [Architecture](/development/architecture)
