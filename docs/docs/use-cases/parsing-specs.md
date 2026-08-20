---
title: "Parsing specs"
description: "Analyze a layout once and reuse deterministic selectors on later crawls"
---

# Parsing specs

`analyze` runs the dynamic heuristics once and distils them into a portable YAML
parsing spec. Feeding that spec back into `extract --spec` skips discovery and
runs deterministic selectors.

```bash
newsworker analyze "https://example.com/news" -o example.yaml
newsworker extract "https://example.com/news" --spec example.yaml --format rss
newsworker spec validate example.yaml
```

The same YAML shape is used inside **site bridges** under a top-level `spec:`
key. See the full [spec format](/guides/parsing-specs) and
[plugins and bridges](/integrations/plugins-and-bridges).
