## 1. Optional plugin
- [x] 1.1 Add a browser extra and Playwright-backed extractor plugin
- [x] 1.2 Add explicit render CLI/config options and dependency diagnostics
- [x] 1.3 Add bounded browser/context pooling and cleanup

## 2. Security and limits
- [x] 2.1 Validate navigation URLs and redirects through the network policy
- [x] 2.2 Intercept/block disallowed subresources where supported
- [x] 2.3 Enforce time, bytes, memory/process, redirect, and concurrency limits
- [x] 2.4 Document required OS/container sandboxing for untrusted pages

## 3. Fallback and diagnostics
- [x] 3.1 Add configurable zero-item diagnostic-driven fallback
- [x] 3.2 Record render provenance, timing, wait condition, and failure reasons
- [x] 3.3 Preserve normal extraction when the browser extra is absent

## 4. Verification
- [x] 4.1 Add deterministic local JS-rendered fixtures
- [x] 4.2 Test blocked navigation/subresources, timeouts, crashes, and cleanup
- [x] 4.3 Benchmark memory/latency and set documented defaults
- [x] 4.4 Run core tests without the extra and browser-specific tests with it
