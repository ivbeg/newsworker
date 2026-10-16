## ADDED Requirements
### Requirement: Connect-time Address Validation
Synchronous fetches SHALL validate the address of every connection as it is opened,
so a hostname that re-resolves to a blocked address after the initial check
(DNS rebinding) SHALL still be rejected.

#### Scenario: Hostname rebinds to loopback
- **WHEN** a public hostname passes the URL check but resolves to `127.0.0.1` when the connection opens
- **THEN** the connection SHALL be refused before any request is sent

### Requirement: Cross-origin Credential Stripping
On a redirect to a different origin, the system SHALL drop `Authorization`,
`Cookie`, `Proxy-Authorization`, `X-API-Key`, `X-Auth-Token` and configured extra
headers.

#### Scenario: Redirect to another host
- **WHEN** a request carrying a configured authorization header is redirected to another host
- **THEN** the redirected request SHALL NOT carry that header

### Requirement: Per-host Politeness
Source fetches SHALL be paced per host: at most `per_host_concurrency` concurrent
requests, at least `per_host_delay` seconds apart, honouring robots.txt
`Crawl-delay` (capped at 60 s) and `Retry-After` on 429/503 responses (capped at
one hour). A request that would wait longer than `max_host_wait` seconds SHALL fail
fast instead of blocking.

#### Scenario: Server asks to retry later
- **WHEN** a host answers `429` with `Retry-After: 120`
- **THEN** further source requests to that host SHALL NOT be sent for 120 seconds
- **AND** a request that cannot start within `max_host_wait` SHALL fail with a rate-limit error

### Requirement: Explicit Proxy Environment
Proxy environment variables SHALL be ignored unless `trust_env_proxy` is enabled.

#### Scenario: HTTPS_PROXY set in the environment
- **WHEN** `HTTPS_PROXY` is set and `trust_env_proxy` is false
- **THEN** requests SHALL connect directly
