---
title: "Local document input"
description: "Extract and analyze archived HTML files and stdin pipelines"
---

# Local and archived document input

`extract` and `analyze` accept either a network URL or a local source. Local
input must have an absolute HTTP(S) base URL so relative links are resolved
exactly as they were on the archived site. Local bytes bypass robots checks,
outbound policy, and the URL content cache.

```bash
newsworker extract --file archive/page.html \
  --base-url https://example.com/news/ --format json

curl --silent https://example.com/news/ \
  | newsworker analyze --file - --base-url https://example.com/news/ \
      --output page-spec.yaml
```

The library equivalent is `DocumentSource.file(...)`,
`DocumentSource.stdin(...)`, or `DocumentSource.url(...)`, followed by
`FeedService.get_feed_source(source)`. Empty input, non-regular files, missing
base URLs, and non-HTTP(S) base URLs fail before extraction.
