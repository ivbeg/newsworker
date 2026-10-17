# feed-extraction Specification

## Purpose
Core extraction from HTML pages: safe fetching, dates, language, per-item fields, full text, plugins, bridges and the async transport.
## Requirements
### Requirement: TLS Verification by Default
The system SHALL verify TLS certificates by default when fetching pages, and SHALL only
skip verification when the user explicitly opts out.

#### Scenario: Verified fetch by default
- **WHEN** a page is fetched without any insecure option
- **THEN** the HTTP client verifies the server's TLS certificate

#### Scenario: Explicit opt-out
- **WHEN** a user passes `--insecure` (or sets `verify_tls: false`)
- **THEN** TLS verification is disabled for that run only

### Requirement: robots.txt Compliance
The system SHALL consult the target site's `robots.txt` before fetching and SHALL refuse
to fetch URLs disallowed for its User-Agent, unless the user opts out.

#### Scenario: Disallowed URL is refused
- **WHEN** the site's `robots.txt` disallows the requested path for the configured User-Agent
- **THEN** the fetch is refused with an error and no page content is retrieved

#### Scenario: Robots retrieval failure is lenient
- **WHEN** `robots.txt` cannot be retrieved
- **THEN** the fetch is permitted to proceed

#### Scenario: Opting out of robots checks
- **WHEN** a user passes `--ignore-robots`
- **THEN** the fetch proceeds regardless of `robots.txt`

### Requirement: Fuzzy Relative Date Parsing
The system SHALL resolve common relative date expressions into absolute datetimes before
delegating to the underlying date parser.

#### Scenario: Resolving "hours ago"
- **WHEN** an item's date text is "2 hours ago" and the reference time is known
- **THEN** the item's `pubdate` is set to two hours before the reference time

#### Scenario: Resolving named relative days
- **WHEN** an item's date text is "yesterday"
- **THEN** the item's `pubdate` resolves to the calendar day before the reference date

### Requirement: Feed Language Detection
The system SHALL detect the feed language from the page rather than always assuming
English, and SHALL allow an explicit override.

#### Scenario: Detecting from the HTML lang attribute
- **WHEN** a page declares `<html lang="fr">`
- **THEN** the produced feed's `language` is `fr`

#### Scenario: Explicit language override
- **WHEN** a user passes `--language de`
- **THEN** the produced feed's `language` is `de` regardless of detection

#### Scenario: Default when undetectable
- **WHEN** no language can be detected and none is supplied
- **THEN** the feed language defaults to `en`

### Requirement: Per-item Author Extraction
The system SHALL extract a per-item author when present and expose it on the feed item and
in the rendered output formats.

#### Scenario: Author from rel=author
- **WHEN** an item contains an element with `rel="author"`
- **THEN** the item's `author` field is populated with that value

#### Scenario: No author present
- **WHEN** an item has no discoverable author
- **THEN** the item's `author` field is absent or null and output remains valid

### Requirement: Per-item Category Extraction
The system SHALL extract per-item categories/tags when present and expose them as a list
on the feed item and in the rendered output formats.

#### Scenario: Categories from tag markup
- **WHEN** an item contains `.tags`, `.categories`, or `rel="tag"` markup
- **THEN** the item's `categories` field is a list of the detected tags

### Requirement: Correct Enclosure Length
The system SHALL NOT emit a hardcoded enclosure length of zero; it SHALL provide the real
`Content-Length` when known or omit the length attribute.

#### Scenario: Unknown enclosure length
- **WHEN** the enclosure length cannot be determined cheaply
- **THEN** the length attribute is omitted rather than reported as zero

### Requirement: Full-article Body Extraction
The system SHALL optionally follow each item link and extract the main article body when
the user requests full text.

#### Scenario: Extracting full text
- **WHEN** a user runs extraction with `--full-text`
- **THEN** each item's body is populated from the linked article's main content

#### Scenario: Full-text dependency absent
- **WHEN** `--full-text` is requested but the extraction dependency is not installed
- **THEN** the command reports a clear error and does not crash

### Requirement: Third-party Extractor Plugins
The system SHALL discover and use custom extractors registered by third-party packages
through a documented entry-point group.

#### Scenario: Registered plugin selected
- **WHEN** an installed package registers an extractor under the `newsworker.extractors` entry-point group that matches a URL
- **THEN** that extractor is used for the URL in preference to the built-in fallback

#### Scenario: No plugin matches
- **WHEN** no registered plugin matches a URL
- **THEN** the built-in spec/dynamic extraction path is used

### Requirement: Per-site Bridges
The system SHALL support per-site bridge definitions that override extraction for sites
with known layouts.

#### Scenario: Bridge matches a host
- **WHEN** a bridge is defined for a host and a matching URL is extracted
- **THEN** the bridge's field rules are applied via `SpecExtractor`

### Requirement: Optional Async Transport
The system SHALL provide an optional asynchronous fetcher for high-throughput batch jobs
while keeping synchronous fetching as the default.

#### Scenario: Async fetcher enabled
- **WHEN** the async extra is installed and async transport is enabled for a batch job
- **THEN** pages are fetched concurrently using the async transport

#### Scenario: Async dependency absent
- **WHEN** the async extra is not installed
- **THEN** the system uses the synchronous transport without error

### Requirement: Native Feed Passthrough
When a source URL already serves an RSS, Atom, RDF or JSON Feed document, the system
SHALL map its entries onto the internal item contract instead of running HTML
extraction, keeping publisher entry ids, dates, authors, categories and content.

#### Scenario: Source is an Atom feed
- **WHEN** `extract` is given a URL whose response body is an Atom feed
- **THEN** the items SHALL come from the feed entries with their published dates and authors
- **AND** each item identity SHALL derive from the entry id when one is present

#### Scenario: Native feeds disabled
- **WHEN** `native_feeds` is set to false
- **THEN** feed documents SHALL be processed by the HTML strategies like any other page

### Requirement: Structured-data Article Lists
The system SHALL read JSON-LD (`ItemList`, `@graph`, article types) and microdata
article lists when date-driven extraction finds no items, and SHALL use structured
dates to fill missing publication dates of extracted items.

#### Scenario: Listing with JSON-LD only
- **WHEN** a page has no recognisable date clusters but publishes a JSON-LD `ItemList` of articles
- **THEN** the feed SHALL contain those articles and diagnostics SHALL name the structured-data strategy

#### Scenario: Structured data disabled
- **WHEN** `structured_data` is set to false
- **THEN** JSON-LD and microdata SHALL be ignored

### Requirement: Plausible Publication Dates
Matched dates SHALL be converted to timezone-aware instants and rejected when they
fall before 1970 or more than one year after the extraction time. Two-digit years
SHALL be expanded relative to the extraction time.

#### Scenario: Version number looks like a date
- **WHEN** a text node such as `1.2.3456` matches a date pattern with year 3456
- **THEN** the match SHALL NOT be used as a publication date

### Requirement: Multilingual Relative Dates
Relative publication dates ("2 hours ago", "вчера", "vor 3 Tagen") SHALL be resolved
against the extraction time in English, Russian, Ukrainian, German, French, Spanish,
Italian and Portuguese.

#### Scenario: Russian relative date
- **WHEN** an item shows `3 часа назад` and the extraction time is 12:00 UTC
- **THEN** the item publication date SHALL be 09:00 UTC on the same day

### Requirement: Empty-result Exit Code
`extract` and `scan` SHALL accept `--fail-on-empty` and exit with code 3 when a
source yields no items, so schedulers can detect broken sources.

#### Scenario: Page layout changed
- **WHEN** `newsworker extract URL --fail-on-empty` extracts zero items
- **THEN** the command SHALL exit with code 3

### Requirement: Datelines, Weekdays and Day Spans
A short date line (at most 64 characters) that does not match as written SHALL
be matched again with a leading label of up to four words before a comma or a
spaced dash removed, and with a leading day span reduced to its first day.
Longer text SHALL NOT be reshaped.

#### Scenario: Press-release dateline
- **WHEN** an item shows `GENEVA, 29 July 2022`
- **THEN** its publication date SHALL be 29 July 2022

#### Scenario: Event span
- **WHEN** an item shows `Bangkok, 21-22 July 2022`
- **THEN** its publication date SHALL be 21 July 2022

#### Scenario: Date inside a sentence
- **WHEN** a paragraph longer than 64 characters mentions `3 May 2022`
- **THEN** the paragraph SHALL NOT be used as a publication date

