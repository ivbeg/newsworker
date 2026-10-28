# feed-discovery Specification

## Purpose
Finding and processing many sources: sitemap-based discovery, OPML import and batch extraction.
## Requirements
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

### Requirement: Bounded Site Crawl Discovery
The `scan` command SHALL accept `--crawl`, which follows same-site links from the given
URL and collects feed candidates from every visited page with the same detectors as a
single-page scan. The crawl SHALL fetch at most `--max-pages` pages (default 50) and
SHALL NOT queue links from pages at `--max-depth` link steps from the start page
(default 2). Pages SHALL be fetched one at a time. `--max-pages` and `--max-depth`
SHALL be positive and SHALL be rejected with exit code 2 when `--crawl` is absent.
Without `--crawl`, `scan` output SHALL be unchanged.

#### Scenario: Feed declared only on a section page
- **WHEN** a user runs `scan https://example.com/ --crawl` and only `/news/` declares an RSS feed with an alternate link
- **THEN** the result SHALL contain that feed as a candidate

#### Scenario: Page bound reached
- **WHEN** a site has more in-scope pages than `--max-pages`
- **THEN** the crawl SHALL stop after fetching `--max-pages` pages
- **AND** the crawl summary SHALL report that it stopped at the bound

#### Scenario: Depth bound
- **WHEN** a page is reached at depth `--max-depth`
- **THEN** its candidates SHALL be collected and its links SHALL NOT be visited

#### Scenario: Bound option without crawl
- **WHEN** a user runs `scan https://example.com/ --max-pages 10` without `--crawl`
- **THEN** the command SHALL exit with code 2

### Requirement: Crawl Link Selection
The crawl SHALL visit only http(s) pages on the start page's effective host, treating
the host with and without one leading `www.` as the same site, and SHALL visit each
normalized URL (fragment removed) at most once. Feed-like URLs and links to non-HTML
resources SHALL NOT be visited as pages; feed-like URLs SHALL remain candidates.
Among links at the same depth, links whose URL or anchor text contains a news-section
hint SHALL be visited before other links, and pagination links SHALL be visited last.

#### Scenario: Off-site link
- **WHEN** a crawled page links to another host
- **THEN** that page SHALL NOT be fetched
- **AND** a feed URL on another host found on a crawled page SHALL still be reported as a candidate

#### Scenario: Link cycle
- **WHEN** pages link to each other in a cycle
- **THEN** each page SHALL be fetched once

#### Scenario: News section first
- **WHEN** the start page links to `/about/` and `/news/` at the same depth and only one more page fits the bound
- **THEN** the crawl SHALL fetch `/news/`

#### Scenario: Document link
- **WHEN** a crawled page links to a PDF file on the same host
- **THEN** the crawl SHALL NOT fetch it

### Requirement: Crawl Politeness
Every page fetch of a crawl SHALL use the shared fetch policy and per-host pacing, and,
when `respect_robots` is enabled, SHALL consult robots.txt first, skip disallowed pages
and apply its `Crawl-delay`. A page that fails to fetch, is disallowed, or is not HTML
SHALL be skipped and counted without stopping the crawl. Only an unreachable start page
SHALL fail the scan.

#### Scenario: Page disallowed by robots.txt
- **WHEN** robots.txt disallows `/private/` and a crawled page links to `/private/list`
- **THEN** `/private/list` SHALL NOT be fetched
- **AND** the crawl summary SHALL count one page skipped for robots

#### Scenario: One page fails
- **WHEN** one crawled page times out
- **THEN** the remaining pages SHALL still be crawled and the failure SHALL be counted

#### Scenario: Start page unreachable
- **WHEN** the start URL cannot be fetched
- **THEN** `scan --crawl` SHALL exit with code 1 as a single-page scan does

### Requirement: Crawl Provenance and Summary
In crawl mode each candidate SHALL list up to five pages it was found on, in visit
order, and the number of such pages. The JSON result SHALL include a crawl summary with
pages fetched, the page and depth bounds, whether the crawl stopped at the page bound
with links left, and skipped pages counted by reason (`robots`, `error`, `not_html`).
CSV output SHALL append a `found_on` column with the first page in crawl mode only.

#### Scenario: Site-wide feed link
- **WHEN** the same feed is linked from the header of every crawled page
- **THEN** one candidate SHALL be reported with a page count equal to the pages it was found on

#### Scenario: CSV without crawl
- **WHEN** a user runs `scan URL -f csv` without `--crawl`
- **THEN** the CSV header SHALL be unchanged

### Requirement: News Listing Candidates
The `scan` command SHALL accept `--listings`, which reports each scanned page that
extraction reads as a news listing with at least three dated items as a candidate with
`feedtype` `html`, source `extraction`, the item count and the extraction confidence.
Extraction SHALL use the already fetched page body and the user's settings. Listing
candidates SHALL NOT be verified as feeds and SHALL be omitted from OPML output.

#### Scenario: Listing page without a feed
- **WHEN** `scan https://example.com/ --crawl --listings` reaches `/news/`, which has no feed but lists ten dated news items
- **THEN** `/news/` SHALL be reported as an `html` candidate with ten entries

#### Scenario: Article page with a few dated links
- **WHEN** a crawled article page has two dated related-news links
- **THEN** it SHALL NOT be reported as a listing candidate

#### Scenario: OPML output
- **WHEN** `scan --listings -f opml` finds one feed and one listing page
- **THEN** the OPML SHALL contain only the feed

