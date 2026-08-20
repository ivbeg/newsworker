---
title: "Browser rendering"
description: "Optional Playwright fallback for client-rendered news listings"
---

# Optional browser rendering

Install the optional renderer with `pip install 'newsworker[browser]'` followed
by `playwright install chromium`. Explicit `--render` always renders; automatic
fallback requires `render_fallback: true` and runs once only when normal
extraction returns zero items and the document has client-rendering signals.

Secure defaults are one concurrent render, a 15-second navigation deadline, a
10 MiB rendered-document cap, the shared five-hop redirect limit, and blocked
media/font or network-policy-violating subresources. Browser contexts and
processes close after every success, timeout, or crash. Run untrusted JavaScript
only inside an OS/container sandbox with an outbound firewall; portable
in-process memory enforcement is not a substitute for a container memory limit.

Reproduce the local no-network baseline with:

```bash
python benchmarks/browser_benchmark.py
```

The benchmark renders a deterministic loopback page five times and reports
median/p95 latency plus parent and browser-child peak RSS. Measurements depend
strongly on browser, OS, and cold/warm cache state, so compare regressions on
the same runner.

The 2026-08-04 baseline on Python 3.13.7, Playwright 1.62/Chromium 151, and
Apple Silicon measured 1,902.5 ms median render latency, a 3,540.7 ms
five-sample maximum, 45.7 MiB parent peak RSS, and 139.8 MiB browser-child peak
RSS. These results support the conservative default concurrency of one;
deployments should enforce a container memory limit sized for their own pages
and measured browser version.

See [benchmarks](/development/benchmarks) and [security](/guides/security).
