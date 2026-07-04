## ADDED Requirements

### Requirement: Conditional Feed Responses
The feed server SHALL send validators (`ETag` and `Last-Modified`) on `/feed` responses
and SHALL honor conditional request headers with `304 Not Modified`.

#### Scenario: Serving validators
- **WHEN** a client requests `/feed` for a page
- **THEN** the response includes an `ETag` and a `Last-Modified` header

#### Scenario: Not-modified response
- **WHEN** a client repeats the request with a matching `If-None-Match`
- **THEN** the server responds with `304 Not Modified` and no body

### Requirement: Conditional Upstream Revalidation
The system SHALL store upstream validators with cached content and SHALL revalidate the
upstream page conditionally on re-fetch.

#### Scenario: Upstream returns 304
- **WHEN** a cached page is re-fetched and the upstream responds `304 Not Modified`
- **THEN** the previously cached content is reused without re-downloading the body

### Requirement: Concurrent Cache Write Safety
The caches SHALL be safe under concurrent writes to the same key, producing no partially
written or corrupted entries.

#### Scenario: Concurrent writers
- **WHEN** multiple server threads write the same cache key simultaneously
- **THEN** the stored entry is always a complete, readable value

### Requirement: Metrics Endpoint
The feed server SHALL expose an optional Prometheus `/metrics` endpoint that is disabled
gracefully when the metrics dependency is unavailable.

#### Scenario: Metrics available
- **WHEN** `prometheus_client` is installed and metrics are enabled
- **THEN** `/metrics` returns request and extraction-latency metrics in Prometheus format

#### Scenario: Metrics dependency absent
- **WHEN** `prometheus_client` is not installed
- **THEN** the server still starts and `/metrics` is disabled without error
