---
title: "Batch pipelines"
description: "Extract feeds from many pages with stable artifacts and a run manifest"
---

# Batch pipelines

`batch` extracts feeds from a list of pages concurrently, writing one file per
URL. Artifact names are stable SHA-1-derived names of the source URL.

```bash
newsworker batch --urls-file urls.txt --output-dir feeds --format rss \
  --manifest run.json --manifest-format json --failure-policy strict

newsworker batch --from-opml subscriptions.opml --output-dir feeds \
  --manifest run.csv --manifest-format csv --failure-policy partial-success
```

Use `--async` with `newsworker[async]` for aiohttp transport.

See [`batch`](/commands/batch) for options and [batch manifests](/guides/batch)
for exit codes and record fields.
