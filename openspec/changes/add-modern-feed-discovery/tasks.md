## 1. Candidate model and detectors
- [x] 1.1 Add a typed candidate with URL, declared type, source, confidence, and verification state
- [x] 1.2 Fix relative/multi-token autodiscovery and duplicate/type preservation
- [x] 1.3 Add JSON Feed and WebSub link detection

## 2. Sitemap traversal
- [x] 2.1 Parse sitemap URL sets and indexes from policy-bounded bytes
- [x] 2.2 Add depth, document, URL, byte, and cycle bounds
- [x] 2.3 Preserve the sitemap source for each candidate

## 3. Verification and CLI
- [x] 3.1 Verify bounded candidates concurrently through the unified fetch policy
- [x] 3.2 Pass bytes rather than URLs to RSS/Atom/JSON Feed parsers
- [x] 3.3 Add explicit verified/no-verify CLI behavior and output status

## 4. Verification and docs
- [x] 4.1 Add RSS, Atom, JSON Feed, WebSub, malformed, redirect, duplicate, and timeout fixtures
- [x] 4.2 Add nested/cyclic/oversized sitemap index tests
- [x] 4.3 Update JSON, CSV, OPML, RSS, and Atom discovery output docs/tests
- [x] 4.4 Run the full test, lint, and type-check suite

