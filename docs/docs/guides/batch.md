---
title: "Batch manifests"
description: "Stable artifacts, run manifests, and batch failure policies"
---

# Batch manifests and automation

Batch mode deduplicates execution while preserving requested input order in its
manifest. Artifact names are stable SHA-1-derived names of the source URL, so
repeated runs map the same source and format to the same path.

```bash
newsworker batch --urls-file urls.txt --output-dir feeds --format json \
  --manifest run.json --manifest-format json --failure-policy strict

newsworker batch --from-opml subscriptions.opml --output-dir feeds \
  --manifest run.csv --manifest-format csv --failure-policy partial-success
```

Each record reports `success`, `partial`, or `failure`, plus artifact path,
elapsed time, transport, cache state, strategy, item count,
confidence/warnings, and a typed redacted error. Strict mode exits 2 after mixed
results and 3 after total failure. Partial-success mode exits successfully when
at least one artifact was written, while retaining every failure in the
manifest.

See [`batch`](/commands/batch).
