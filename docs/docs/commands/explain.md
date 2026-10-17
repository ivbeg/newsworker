---
title: "explain"
description: "newsworker explain command reference"
---

# `explain`

Shows why a page yields the items it does: every repeated group of dates on the
page and which one was chosen, the strategies that were tried, the spec a fresh
analysis would write, the resulting items, and plain-language hints when the
result looks wrong.

```bash
newsworker explain URL [OPTIONS]
newsworker explain --file page.html --base-url https://example.com/news [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--format` | `-f` | `text` | `text`, `html` (standalone report) or `json`. |
| `--output` | `-o` | *(stdout)* | Write the report to a file. |
| `--file` / `--base-url` | | — | Explain a saved page (`-` reads stdin). |
| `--render` | | `false` | Render with the browser extra first. |
| `--undated` | | `false` | Allow the undated-listing fallback. |
| `--no-cache` | | `false` | Ignore cached specs and pages. |
| `--user-agent`, `--ignore-robots`, `--config`, `--verbose` | | | As for `extract`. |

```bash
newsworker explain "https://example.com/news" -f html -o report.html
```

Hints cover the common failure modes: no repeated dates (try `--render` or
`--undated`), a chosen date group without links (a calendar or archive menu),
items that all link to the listing page, undated items, a cached spec that was
rebuilt because the layout changed, and items taken from JSON-LD or the
undated fallback.

The HTML report escapes all page content and blocks scripts with a
Content-Security-Policy, so it is safe to open for any page.
