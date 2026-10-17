## MODIFIED Requirements
### Requirement: Native Feed Passthrough
When a source URL already serves an RSS, Atom, RDF or JSON Feed document, the system
SHALL map its entries onto the internal item contract instead of running HTML
extraction, keeping publisher entry ids, dates, authors, categories, content,
enclosures, media and the feed image. Every enclosure SHALL be kept whatever its media
type, with the declared type and a positive declared length; an undeclared or zero
length SHALL be kept as unknown. All entry authors SHALL be kept in order in `authors`,
with `author` set to the first. The publication date SHALL come from the published
date, else the updated date, and a differing updated date SHALL be kept as `modified`.

#### Scenario: Source is an Atom feed
- **WHEN** `extract` is given a URL whose response body is an Atom feed
- **THEN** the items SHALL come from the feed entries with their published dates and authors
- **AND** each item identity SHALL derive from the entry id when one is present

#### Scenario: Native feeds disabled
- **WHEN** `native_feeds` is set to false
- **THEN** feed documents SHALL be processed by the HTML strategies like any other page

#### Scenario: Podcast enclosure
- **WHEN** an RSS item carries `<enclosure url="https://example.com/ep1.mp3" length="12345" type="audio/mpeg"/>`
- **THEN** the item's `extra.enclosures` SHALL contain that URL with type `audio/mpeg` and length `12345`

#### Scenario: Enclosure without a length
- **WHEN** an RSS item carries an enclosure with `length="0"`
- **THEN** the enclosure SHALL be kept with an unknown length

#### Scenario: Media RSS thumbnail
- **WHEN** an RSS item carries `<media:thumbnail url="https://example.com/ep1.jpg"/>`
- **THEN** that URL SHALL be among the item's images

#### Scenario: Several authors
- **WHEN** an RSS item carries `<dc:creator>Alice</dc:creator><dc:creator>Bob</dc:creator>`
- **THEN** the item's `authors` SHALL be `["Alice", "Bob"]` and its `author` SHALL be `Alice`

#### Scenario: Published and updated dates
- **WHEN** an Atom entry has `published` 2026-10-12T10:00:00Z and `updated` 2026-10-13T08:00:00Z
- **THEN** the item's `pubdate` SHALL be the published instant and its `modified` SHALL be the updated instant

#### Scenario: Channel image
- **WHEN** an RSS channel declares `<image><url>https://example.com/logo.png</url>…</image>`
- **THEN** the feed's `image` SHALL be `https://example.com/logo.png`

### Requirement: Full-article Body Extraction
The system SHALL optionally follow each item link and extract the main article body when
the user requests full text. Full text SHALL run as the built-in `fulltext` enricher:
article pages SHALL be fetched through the shared article stage (content cache and
outbound fetch policy), and an item whose content already reaches
`enrich_min_content_chars` SHALL keep its content and SHALL NOT be fetched for full text.

#### Scenario: Extracting full text
- **WHEN** a user runs extraction with `--full-text`
- **THEN** each item's body is populated from the linked article's main content

#### Scenario: Full-text dependency absent
- **WHEN** `--full-text` is requested but the extraction dependency is not installed
- **THEN** the command reports a clear error and does not crash

#### Scenario: Full text on a feed with complete bodies
- **WHEN** `--full-text` is requested for a feed whose entries carry complete `content:encoded` bodies
- **THEN** the entries SHALL keep their native content and their article pages SHALL NOT be fetched

#### Scenario: Repeated full-text build
- **WHEN** the same feed is built twice with `--full-text` within `content_ttl`
- **THEN** the second build SHALL take the article pages from the content cache
