# modern-feed-discovery Specification

## Purpose
Discovery of current feed formats and hubs: JSON Feed, bounded sitemap indexes, candidate provenance, concurrent verification and WebSub.

## Requirements
### Requirement: JSON Feed Discovery
Feed discovery SHALL recognize JSON Feed declarations and verified JSON Feed documents.

#### Scenario: HTML advertises JSON Feed
- **WHEN** a page contains an alternate link with JSON Feed media type
- **THEN** discovery SHALL return an absolute candidate labeled `jsonfeed`

#### Scenario: Candidate is not valid JSON Feed
- **WHEN** verification parses a declared JSON Feed that lacks required structure
- **THEN** the candidate SHALL be marked invalid rather than accepted as RSS

### Requirement: Bounded Sitemap-index Traversal
Discovery SHALL traverse sitemap indexes only within configured depth, document, URL,
byte, and time bounds.

#### Scenario: Nested sitemap contains a feed
- **WHEN** a permitted nested sitemap lists a feed-like URL within all bounds
- **THEN** discovery SHALL return the candidate with its sitemap provenance

#### Scenario: Sitemap cycle
- **WHEN** sitemap indexes refer to an already visited document
- **THEN** discovery SHALL skip the cycle without repeated fetching

### Requirement: Candidate Type and Provenance Preservation
Discovery SHALL preserve the strongest known type, source, confidence, and verification
state while deduplicating candidates by normalized URL.

#### Scenario: Atom candidate appears through two detectors
- **WHEN** autodiscovery and a sitemap identify the same Atom URL
- **THEN** one result SHALL retain the Atom type and both applicable provenance signals

### Requirement: Bounded Concurrent Verification
Candidate verification SHALL use bounded concurrency and the shared network fetch policy.

#### Scenario: One candidate times out
- **WHEN** one feed candidate exceeds its timeout
- **THEN** other candidates SHALL continue and the timed-out result SHALL carry a verification error

### Requirement: WebSub Relationship Discovery
Discovery SHALL capture valid WebSub hub and self relationships advertised by a feed or page.

#### Scenario: Feed advertises a hub
- **WHEN** a verified feed contains valid hub and self links
- **THEN** the discovery result SHALL expose those relationships without subscribing automatically

