## ADDED Requirements
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
