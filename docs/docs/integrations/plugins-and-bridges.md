---
title: "Plugins and bridges"
description: "Third-party extractors and YAML site bridges for known layouts"
---

# Plugins and site bridges

## Plugins

Third-party plugins register extractors via the `newsworker.extractors`
setuptools entry-point group. Each plugin implements `matches(url)` and
`extract(url, data=None, **kwargs)` returning the internal feed dict. Matching
plugins are consulted before built-in spec/dynamic extraction.

## Site bridges

Site bridges are YAML files with a `match:` block (`host`, optional `path`
fnmatch) and a `spec:` body (the same shape as an `analyze` spec). Bundled
examples live under `newsworker/bridges/`; drop overrides in
`~/.newsworker/bridges/` (or set `bridges_dir` in config). When a URL matches,
the bridge spec is applied without running heuristics.

```yaml
match:
  host: example.com
  path: /news*
spec:
  version: 1
  items:
    selector: li.news-item
  fields:
    date: {selector: span.date, source: text, required: true}
    title: {selector: a, source: text}
    link: {selector: a, source: attr:href, absolute: true}
```

## Delivery channels

Third-party packages may register watch destinations in the
`newsworker.delivery` entry-point group. See [delivery](/guides/delivery).

## Async batch

`batch --async` uses `aiohttp` when the `[async]` extra is installed; otherwise
the command falls back to the default thread pool.
