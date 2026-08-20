---
title: "cache"
description: "newsworker cache command reference"
---

# `cache`

Inspects or clears the spec and content caches. See [Settings](/guides/settings).

```bash
newsworker cache stats            # entry counts and total size per cache
newsworker cache list             # list cached entries
newsworker cache clear            # delete all cached specs and content
newsworker cache clear --content  # scope to a single cache (--specs / --content)
```

`--config` / `-c` selects the settings file that determines `cache_dir`.
