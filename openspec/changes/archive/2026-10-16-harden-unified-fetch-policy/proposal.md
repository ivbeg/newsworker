# Change: Harden and unify outbound fetch policy

## Why
The main extractor enforces TLS, robots, timeouts, retries, and response limits, but
feed discovery, async batch, robots retrieval, redirects, full-text, pagination, and
webhooks apply inconsistent subsets of those controls. The current URL guard also
allows private and link-local addresses, leaving server deployments exposed to SSRF.

## What Changes
- Introduce shared `FetchPolicy` and `FetchResult` contracts for outbound operations.
- Enforce scheme, host, resolved-address, redirect, timeout, TLS, byte-limit, retry,
  robots, proxy, header, cookie, and allow-list rules consistently.
- Block unsafe IPv4/IPv6 destinations by default with an explicit intranet opt-out.
- Validate every redirect hop and preserve requested/effective URL and response metadata.
- Migrate sync extraction, async batch, finder verification, robots, pagination,
  full-text, and webhook calls to the shared policy.
- Keep SHA-1 cache keys based on the requested URL.

## Impact
- Affected specs: `network-fetch-policy`
- Affected code: `newsworker/extractor.py`, `newsworker/async_fetch.py`,
  `newsworker/finder.py`, `newsworker/tools.py`, `newsworker/service.py`,
  `newsworker/delivery.py`, settings, security tests
- Dependencies: coordinates with `refactor-request-runtime`; server access controls are
  a separate proposal

