## ADDED Requirements

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

