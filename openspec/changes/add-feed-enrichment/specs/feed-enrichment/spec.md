## ADDED Requirements
### Requirement: Enricher Selection
The system SHALL run per-item enrichers only when they are named in the `enrich`
setting or the `--enrich` option of `extract`, `batch`, `watch` and `serve`, in the
order given. `--full-text` and `full_text: true` SHALL be equivalent to adding the
built-in `fulltext` enricher. An unknown enricher name SHALL fail configuration
validation before any network work, naming the available enrichers.

#### Scenario: Enrichment not configured
- **WHEN** `enrich` is empty and full text is not requested
- **THEN** no article page SHALL be fetched and the feed SHALL contain only what the strategy produced

#### Scenario: Two enrichers selected
- **WHEN** a user runs `extract FEED_URL --enrich metadata,fulltext -f atom`
- **THEN** `metadata` SHALL run before `fulltext` for every item that needs enrichment

#### Scenario: Misspelled enricher
- **WHEN** `enrich` contains `metdata`
- **THEN** the command SHALL fail before fetching and the message SHALL list `metadata` and `fulltext` among the available enrichers

### Requirement: Shared Article Fetch
When a selected enricher needs the article page, the system SHALL fetch each distinct
item link at most once per feed build, through the content cache and the outbound
fetch policy (robots.txt, size cap, private-address protection, per-host pacing), and
SHALL give the same fetched document to every selected enricher.

#### Scenario: Feed rebuilt within the cache lifetime
- **WHEN** the feed server rebuilds an enriched feed whose article pages were fetched less than `content_ttl` seconds ago
- **THEN** the article pages SHALL be served from the content cache without contacting the sites

#### Scenario: Two enrichers need the article
- **WHEN** `metadata` and `fulltext` are both selected for an item
- **THEN** the item's link SHALL be fetched once

#### Scenario: Article page disallowed by robots.txt
- **WHEN** an item's article page is disallowed by robots.txt
- **THEN** the item SHALL be left unchanged and the build SHALL report how many items could not be enriched

#### Scenario: Link serves a PDF
- **WHEN** an item link answers with a non-HTML content type
- **THEN** enrichers that need the article page SHALL NOT be given a document for that item

### Requirement: Article Fetch Skip Rule and Budget
The system SHALL NOT fetch an item's article page when no selected enricher declares
a field that is missing on the item. Content SHALL count as missing when absent or
when its plain text is shorter than `enrich_min_content_chars`. At most
`enrich_max_items` items per build SHALL be fetched (0 means no limit), in feed order.

#### Scenario: Native feed already carries full bodies
- **WHEN** only `fulltext` is selected and every entry of a source feed has `content:encoded` longer than `enrich_min_content_chars`
- **THEN** no article page SHALL be fetched and the native content SHALL be kept

#### Scenario: Teaser in content
- **WHEN** only `fulltext` is selected and an entry's content is a 120-character teaser
- **THEN** the article page SHALL be fetched and the extracted body SHALL replace the teaser

#### Scenario: Budget reached
- **WHEN** `enrich_max_items` is 10 and 25 items need enrichment
- **THEN** only the first 10 items in feed order SHALL be fetched and the other 15 SHALL be emitted unchanged

### Requirement: Fill-only Enrichment
Enrichers SHALL only add values to fields that are missing on the item and SHALL NOT
replace values provided by the source. A description equal to the item title SHALL
count as missing. When several enrichers can fill a field, the first in `enrich`
order that produces a value SHALL win. Item identity SHALL NOT change because of
enrichment.

#### Scenario: Source author kept
- **WHEN** a native entry has author `Alice` and the article page declares author `Editorial Team`
- **THEN** the item's author SHALL remain `Alice`

#### Scenario: Description that repeats the title
- **WHEN** an item's description equals its title and the article declares an `og:description`
- **THEN** the item's description SHALL become the `og:description` value

#### Scenario: Identity after enrichment
- **WHEN** an item is enriched
- **THEN** its `unique_id` SHALL equal the value it had before enrichment

### Requirement: Article Metadata Enricher
The built-in `metadata` enricher SHALL fill missing `pubdate`, `modified`, `author`,
`authors`, `categories`, `description` and image from the article page, preferring
the page's own JSON-LD article object, then OpenGraph and `article:*` properties, then
standard meta tags. Dates SHALL pass the same plausibility checks as extracted dates.
URLs SHALL be absolute http(s) URLs that pass link sanitising. When the article fetch
was redirected, the item link SHALL become the cleaned final URL; a differing
canonical URL SHALL be recorded in `extra.canonical_url` without replacing the link.
A description or image that the enricher would apply to at least three items and at
least half of the enriched items of one build SHALL NOT be applied.

#### Scenario: Undated listing item
- **WHEN** an item from the undated fallback has no `pubdate` and its article publishes JSON-LD `datePublished` `2026-10-14T09:30:00+02:00`
- **THEN** the item's `pubdate` SHALL be `2026-10-14T07:30:00+00:00`

#### Scenario: Several unrelated JSON-LD articles
- **WHEN** an article page carries several JSON-LD article objects and none matches the page URL
- **THEN** JSON-LD SHALL NOT be used and OpenGraph and meta values SHALL be considered instead

#### Scenario: Implausible article date
- **WHEN** the article declares `datePublished` in the year 3456
- **THEN** the item's `pubdate` SHALL stay unset

#### Scenario: Redirecting tracking link
- **WHEN** an item link redirects to `https://site.example/news/42?utm_source=feed`
- **THEN** the item link SHALL be `https://site.example/news/42`

#### Scenario: Site-wide description
- **WHEN** every article of a 10-item build carries the same `og:description`
- **THEN** that description SHALL NOT be applied to any item

#### Scenario: Image from the article
- **WHEN** an item has no image and the article declares `og:image` without type or size
- **THEN** the image URL SHALL be added to the item's images and no enclosure SHALL be emitted for it

### Requirement: Enrichment Provenance
Every field filled by an enricher SHALL be recorded in the item's `extra.enriched`
mapping with its source (`json-ld`, `opengraph`, `meta`, `redirect`, `trafilatura`,
`readability` or `plugin:<name>`). The feed's provenance SHALL list the enrichers that
ran. Fetch counts and cache state SHALL be reported through diagnostics and SHALL NOT
be part of the feed, so unchanged inputs render to identical output.

#### Scenario: JSON output of an enriched item
- **WHEN** `metadata` fills an item's `pubdate` from JSON-LD and its image from `og:image`
- **THEN** the item's `extra.enriched` SHALL be `{"pubdate": "json-ld", "image": "opengraph"}`

#### Scenario: Rebuild from cache
- **WHEN** an enriched feed is built twice from the same cached listing and article pages
- **THEN** both renderings SHALL be byte-identical

### Requirement: Enricher Plugins
The system SHALL discover third-party enrichers registered under the
`newsworker.enrichers` entry-point group and SHALL run one only when its name is
selected. An enricher SHALL receive the item and the already-fetched article document,
and only values for fields it declares SHALL be applied. An exception raised by one
enricher SHALL leave that enricher's fields unfilled for the item, add a warning, and
SHALL NOT stop other enrichers or items.

#### Scenario: Installed but not selected
- **WHEN** a package registers a `summary` enricher and `enrich` does not name it
- **THEN** the enricher SHALL NOT run

#### Scenario: Plugin fills a declared field
- **WHEN** a selected plugin `summary` declares `description` and returns one for an item without a description
- **THEN** the item's description SHALL be set and `extra.enriched.description` SHALL be `plugin:summary`

#### Scenario: Plugin returns an undeclared field
- **WHEN** a plugin that declares only `categories` returns a `pubdate`
- **THEN** the `pubdate` SHALL be ignored

#### Scenario: Plugin raises
- **WHEN** a selected plugin raises for one item
- **THEN** the other enrichers SHALL still run for that item and the plugin SHALL still run for the remaining items
