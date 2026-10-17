## 1. Policy model
- [x] 1.1 Add typed request, policy, result, and error models
- [x] 1.2 Add normalized hostname and resolved IPv4/IPv6 classification
- [x] 1.3 Add validated manual redirect handling and effective-URL metadata

## 2. Transport adapters
- [x] 2.1 Wrap the requests transport with the shared policy
- [x] 2.2 Implement an aiohttp adapter with equivalent policy behavior
- [x] 2.3 Fetch and parse robots content through the bounded policy path
- [x] 2.4 Pass already-fetched bytes to feedparser verification

## 3. Caller migration
- [x] 3.1 Migrate extraction, discovery, sitemap, pagination, and full-text GETs
- [x] 3.2 Migrate webhook POSTs to the applicable destination policy
- [x] 3.3 Propagate requested/effective URL, validators, language, status, and headers
- [x] 3.4 Preserve requested-URL cache keys and server allow-list behavior

## 4. Configuration and documentation
- [x] 4.1 Add private-network blocking, redirect-limit, and trusted-proxy settings
- [x] 4.2 Document secure defaults and explicit intranet/proxy opt-ins
- [x] 4.3 Harden Docker/Compose published-port examples

## 5. Verification
- [x] 5.1 Add an SSRF corpus for IPv4, IPv6, encoded hosts, user-info, redirects, and DNS changes
- [x] 5.2 Add sync/async conformance tests for every policy option
- [x] 5.3 Add bounded robots, feed verification, full-text, and webhook tests
- [x] 5.4 Run the full test, lint, type-check, and Docker smoke suite
