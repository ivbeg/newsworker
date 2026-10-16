# feed-server Specification

## Purpose
Serving generated feeds over HTTP efficiently: conditional responses, upstream revalidation, cache write safety and metrics.
## Requirements
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

### Requirement: Signed Feed Links
When `feed_signing_key` is configured, `GET /feed` SHALL require either a valid API
token or a `sig` parameter equal to the HMAC-SHA256 of the requested format and
source URL. A signature SHALL authorise only that exact URL and format.

#### Scenario: Reader uses a signed link
- **WHEN** a feed reader requests `/feed?url=U&format=rss&sig=S` with a valid `S` and no API token
- **THEN** the server SHALL serve the feed

#### Scenario: Signature reused for another source
- **WHEN** the same `sig` is sent with a different `url`
- **THEN** the server SHALL answer 401

### Requirement: Public Subscription URLs
`newsworker feed-url URL` SHALL print the subscription URL for a source, using
`public_base_url` when set and signing it when a signing key is configured. Feed
self links SHALL use the same URL and SHALL NOT contain API tokens.

#### Scenario: Server behind a reverse proxy
- **WHEN** `public_base_url` is `https://feeds.example.org` and a signing key is set
- **THEN** `feed-url` SHALL print `https://feeds.example.org/feed?url=...&format=rss&sig=...`

