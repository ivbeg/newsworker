# network-fetch-policy Specification

## Purpose
One outbound fetch policy for every network operation: SSRF protection, redirect validation, bounded responses and fetch metadata.
## Requirements
### Requirement: Uniform Outbound Fetch Policy
Every outbound network operation SHALL apply the controls relevant to its operation from
one shared policy contract.

#### Scenario: Async batch fetch
- **WHEN** async transport fetches the same source as synchronous transport
- **THEN** both transports SHALL enforce equivalent URL, TLS, timeout, redirect, size, header, proxy, cookie, and robots settings

#### Scenario: Feed candidate verification
- **WHEN** feed discovery verifies a candidate
- **THEN** the verifier SHALL parse policy-bounded bytes and SHALL NOT ask the parser library to fetch the URL

### Requirement: Private-network SSRF Protection
The default policy SHALL reject destinations resolving to unsafe local or special-use
address ranges.

#### Scenario: Private IPv4 destination
- **WHEN** a source or redirect resolves to loopback, private, link-local, multicast, unspecified, or reserved IPv4 space
- **THEN** the request SHALL be rejected before response content is read

#### Scenario: Private IPv6 destination
- **WHEN** a source or redirect resolves to loopback, private, link-local, multicast, unspecified, or reserved IPv6 space
- **THEN** the request SHALL be rejected before response content is read

#### Scenario: Explicit intranet access
- **WHEN** an operator explicitly enables intranet access and allow-lists the destination
- **THEN** the policy MAY permit that destination while retaining all other controls

### Requirement: Redirect-hop Validation
The system SHALL validate every redirect destination under the same address and host
rules as the original request.

#### Scenario: Public URL redirects to a blocked address
- **WHEN** an allowed public source redirects to a private or disallowed host
- **THEN** the redirect SHALL be rejected

#### Scenario: Redirect limit exceeded
- **WHEN** a response chain exceeds the configured redirect limit
- **THEN** the request SHALL fail with a typed redirect error

### Requirement: Bounded Network Responses
Every network response body consumed by the system SHALL be subject to an operation-
appropriate byte limit and timeout.

#### Scenario: Chunked response exceeds its limit
- **WHEN** a response without a usable content length exceeds the byte cap while streaming
- **THEN** reading SHALL stop and the operation SHALL fail without retaining the oversized body

#### Scenario: Robots response stalls
- **WHEN** robots retrieval exceeds the configured timeout
- **THEN** the existing lenient or strict robots failure policy SHALL be applied without blocking indefinitely

### Requirement: Fetch Result Metadata
Successful source fetches SHALL expose the requested URL, effective URL, status, headers,
validators, content language, and body as one result.

#### Scenario: Source redirects to a final page
- **WHEN** a validated redirect chain completes
- **THEN** relative document links SHALL resolve against the effective URL while the cache key remains derived from the requested URL

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

### Requirement: Asynchronous Transport Parity
The asynchronous batch transport SHALL validate the addresses it connects to,
strip credentials and configured headers on cross-origin redirects, scope
cookies from `cookies_file` to their domains, honour `trust_env_proxy`, and use
the content cache with conditional revalidation like the threaded transport.

#### Scenario: Name rebinds to loopback during an async batch
- **WHEN** a source host resolves to `127.0.0.1` at connection time
- **THEN** the async transport SHALL refuse the connection before sending a request

#### Scenario: Second async batch over the same pages
- **WHEN** a page fetched by an earlier batch is still fresh in the content cache
- **THEN** the async batch SHALL reuse it without a request
- **AND** a stale copy SHALL be revalidated with `If-None-Match` / `If-Modified-Since`

### Requirement: Opt-in Legacy TLS Ciphers
The fetch policy SHALL offer only Python's default TLS cipher suites unless
`legacy_tls_ciphers` is enabled (setting, `NEWSWORKER_LEGACY_TLS_CIPHERS`, or
`--legacy-tls-ciphers` on `analyze` and `extract`). When enabled, the requests
and asynchronous transports SHALL also offer TLS 1.2 suites with static RSA key
exchange, while certificate and host-name verification stay as configured by
`verify_tls`. A TLS handshake failure while the option is disabled SHALL report
an error that names the flag and the setting.

#### Scenario: Server accepts only static-RSA suites
- **WHEN** a server offers only `AES256-GCM-SHA384` over TLS 1.2 and `legacy_tls_ciphers` is false
- **THEN** the fetch SHALL fail with an error suggesting `--legacy-tls-ciphers`

#### Scenario: Option enabled
- **WHEN** the same server is fetched with `legacy_tls_ciphers` enabled
- **THEN** the handshake SHALL succeed and the page SHALL be returned

#### Scenario: Certificates still verified
- **WHEN** `legacy_tls_ciphers` is enabled, `verify_tls` is true and the server certificate is self-signed
- **THEN** the fetch SHALL fail certificate verification

#### Scenario: Default requests unaffected
- **WHEN** a default-policy request follows a legacy request to the same host in one session
- **THEN** it SHALL NOT reuse the legacy connection pool

