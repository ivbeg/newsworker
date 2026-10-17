## Context
Outbound HTTP is performed by `requests`, aiohttp, `RobotFileParser`, and feedparser.
Only the primary requests path is streamed and bounded. The server validates the first
URL but extracted links and redirects can leave its allow-list.

## Goals / Non-Goals
- Goals: one enforceable policy, private-network SSRF defense, redirect validation,
  transport parity, bounded reads, and explicit response metadata.
- Non-Goals: provide a general-purpose HTTP client or silently permit intranet crawling.

## Decisions
- Decision: define transport-neutral `FetchRequest`, `FetchPolicy`, and `FetchResult`
  models; adapters implement sync and async I/O.
- Decision: resolve hostnames and reject loopback, private, link-local, multicast,
  unspecified, reserved, and disallowed addresses for both IPv4 and IPv6 by default.
- Decision: follow redirects hop by hop through policy validation with a finite limit.
- Decision: separate source-fetch and delivery-post operations while sharing address,
  TLS, timeout, redirect, and size policy primitives.
- Decision: feedparser receives already-fetched bounded bytes and never fetches a URL.
- Decision: robots files are retrieved with the same timeout, size cap, and session
  policy as source pages, but their failure remains lenient unless configured otherwise.
- Alternatives considered: validating only the final URL leaves redirect and DNS races;
  relying only on `allowed_hosts` does not protect default open-host deployments.

## Risks / Trade-offs
- DNS rebinding between validation and connection -> use resolved-address-aware adapters
  or re-check the connected peer where the transport exposes it.
- Proxies resolve destinations remotely -> document the reduced local verification and
  require an explicit trusted-proxy mode.
- Legitimate intranet users are blocked -> provide a narrowly named opt-in and allow-list.
- Async and sync libraries differ -> enforce behavioral conformance tests at the policy
  boundary rather than identical internal implementations.

## Migration Plan
Introduce the models and wrap the existing requests fetcher, migrate finder/robots and
secondary links, then implement the aiohttp adapter. Keep old method signatures as
deprecated wrappers for one minor release.

## Open Questions
- Which peer-address APIs are portable enough for DNS-rebinding checks in requests and aiohttp?
- Should robots retrieval have a smaller independent byte cap?

