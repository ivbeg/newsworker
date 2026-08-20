---
title: "spec"
description: "newsworker spec command reference"
---

# `spec`

Validate a parsing spec without fetching its source URL.

```bash
newsworker spec validate example.yaml
```

Success prints `valid: example.yaml`. Invalid specs exit with code 1 and an
`invalid: …` message. See [parsing specs](/guides/parsing-specs) and
[diagnostics](/guides/diagnostics).
