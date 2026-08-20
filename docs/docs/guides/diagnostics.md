---
title: "Extraction diagnostics"
description: "Spec validation, --explain traces, and confidence scores"
---

# Extraction diagnostics

Parsing specs have versioned validation and precise field paths. Validate one
without a network request using `newsworker spec validate spec.yaml` or
`FeedSpec.validate()`.

Use `--explain` for a short human trace or `--explain-json` for the stable
diagnostic model. It reports attempted strategies, selector/item counts, reason
codes, timing, warnings, effective URL, and a heuristic confidence score. The
score is a review aid, not a correctness probability: complete repeated items
raise it, while zero items and missing core fields lower it. Server clients may
opt into bounded confidence and warning headers with `diagnostics=1`.

Configured credentials are redacted before diagnostics or batch errors are
serialized.

See [`extract`](/commands/extract) and [`spec`](/commands/spec).
