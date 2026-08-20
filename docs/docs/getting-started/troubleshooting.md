---
title: "Troubleshooting"
description: "Common extraction, fetch, and spec failures and how to inspect them"
---

# Troubleshooting

## No items extracted

1. Confirm the page is a **listing** with visible publication dates, not an
   article body or a JavaScript-only grid.
2. Run with `--explain` (see [diagnostics](/guides/diagnostics)).
3. If the listing truly has no dates, try the opt-in
   [undated fallback](/guides/undated).
4. If the page is client-rendered, try [browser rendering](/guides/browser-rendering).

## `analyze` fails

Typical CLI errors:

| Message | Meaning |
|---------|---------|
| `No dated news listings detected` | No date clusters on the page |
| `Could not group them into individual news items` | Dates found but item roots could not be derived |
| `Could not derive title or link extraction rules` | Item structure too minimal for heuristics |
| `matched fewer than 2 news items` | Selectors do not reproduce the discovered listing |
| `could not parse dates` | Date selectors or patterns fail on sample items |

For pages without a news listing, use dynamic extraction (`extract` without
`--spec`) or a hand-written [site bridge](/integrations/plugins-and-bridges).

## Fetch blocked or empty

- TLS failures: only use `--insecure` when you understand the risk.
- `robots.txt` denials: `--ignore-robots` overrides per run; the default is to honor robots.
- Private/loopback hosts are blocked unless you opt into intranet crawling. See
  [security](/guides/security) and [runtime configuration](/guides/runtime-configuration).
- Oversized responses are capped by `max_content_bytes`.

## Spec extracts the wrong cluster

Tighten `items.selector`, re-run `analyze`, or write a site bridge. Validate a
spec without fetching:

```bash
newsworker spec validate example.yaml
```

## Dates look wrong

- HTML offsets are converted to timezone-aware UTC instants.
- Naive qddate/fuzzy values use `default_timezone` (UTC by default).
- RSS/Atom require UTC; timezone-naive HTML dates are treated as UTC.

See [migration notes](/guides/migration-1-4).

## Language is `en` on a localized page

Automatic language detection uses `<html lang>`, `Content-Language`, and item
text samples. Pass `--language` to override. See
[language support](/guides/language-support).
