---
title: "languages"
description: "newsworker languages command reference"
---

# `languages`

Prints the [language support matrix](/guides/language-support): for each
language, whether dates, page metadata and page text are recognised, and
whether end-to-end extraction is supported or partial.

```bash
newsworker languages [--format text|json|markdown]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--format` | `-f` | `text` | `text` table, `json` (one object per language with its evidence file) or the `markdown` table used in the documentation. |

```bash
newsworker languages
newsworker languages -f json | jq -r '.[] | select(.extraction == "supported") | .code'
```
