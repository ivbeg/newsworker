## ADDED Requirements

### Requirement: Sitemap-based Feed Discovery
The `scan` command SHALL discover candidate feeds by fetching and parsing the site's
`sitemap.xml` in addition to page autodiscovery.

#### Scenario: Discovering feeds from a sitemap
- **WHEN** a scanned site exposes `/sitemap.xml` referencing feed-like URLs
- **THEN** those URLs appear in the scan results alongside autodiscovered feeds

#### Scenario: No sitemap present
- **WHEN** a scanned site has no reachable `sitemap.xml`
- **THEN** scanning still returns autodiscovered feeds without error

### Requirement: OPML Subscription Import
The `scan` command SHALL accept an OPML subscription list and scan each outlined URL.

#### Scenario: Scanning from OPML
- **WHEN** a user runs `scan --from-opml subs.opml`
- **THEN** each outline URL in the OPML file is scanned and its results reported

### Requirement: Batch Feed Extraction
The CLI SHALL provide a `batch-feeds` command that extracts a feed for each URL in an
OPML file into an output directory, isolating per-URL failures.

#### Scenario: Batch extracting an OPML file
- **WHEN** a user runs `batch-feeds feeds.opml -o out/`
- **THEN** one output file is written per OPML outline into `out/`

#### Scenario: One URL fails
- **WHEN** extraction fails for a single outline during a batch run
- **THEN** an error is recorded for that URL and the remaining URLs are still processed
