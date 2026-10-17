## ADDED Requirements
### Requirement: Enclosure and Media Rendering
Formats that support enclosures SHALL emit the item's enclosures, subject to the
truthful enclosure metadata rule. RSS SHALL emit one `<enclosure>`, chosen from the
enclosures with known type and length with audio and video first, plus a Media RSS
`media:content` element for every enclosure with the attributes that are known and a
`media:thumbnail` for the first image. Atom SHALL emit a `link rel="enclosure"` and
JSON Feed an `attachments` entry for every enclosure with known type and length.

#### Scenario: Podcast feed round trip
- **WHEN** a native RSS item with an `audio/mpeg` enclosure of length `12345` is rendered as RSS
- **THEN** the output item SHALL contain `<enclosure url="https://example.com/ep1.mp3" length="12345" type="audio/mpeg"/>`

#### Scenario: Enclosure with unknown length
- **WHEN** an enclosure has a known type and an unknown length
- **THEN** RSS SHALL emit `media:content` for it without `fileSize` and SHALL NOT emit `<enclosure>` for it
- **AND** Atom and JSON Feed SHALL NOT emit it as an enclosure or attachment

#### Scenario: Atom attachments
- **WHEN** an item has two enclosures with known type and length
- **THEN** the Atom entry SHALL contain two `link rel="enclosure"` elements with `type` and `length`

### Requirement: Multiple Authors
Formats with author elements SHALL emit every entry of the item's `authors`, falling
back to `author`: RSS as one `dc:creator` per author, Atom as one `<author>` per
author, and JSON Feed as the `authors` list.

#### Scenario: Two authors in Atom
- **WHEN** an item has `authors` `["Alice", "Bob"]`
- **THEN** the Atom entry SHALL contain two `<author>` elements named `Alice` and `Bob`

#### Scenario: Two authors in RSS
- **WHEN** the same item is rendered as RSS
- **THEN** the item SHALL contain `<dc:creator>Alice</dc:creator>` and `<dc:creator>Bob</dc:creator>`

### Requirement: Modification Dates
When an item has a `modified` instant, Atom SHALL emit it as `<updated>` with the
publication instant as `<published>`, and JSON Feed SHALL emit it as `date_modified`.
The feed-level update time SHALL be the newest of all item publication and
modification instants.

#### Scenario: Corrected article
- **WHEN** an item was published on 2026-10-12 and modified on 2026-10-13
- **THEN** the Atom entry SHALL have `<published>` on 2026-10-12 and `<updated>` on 2026-10-13

#### Scenario: Item never modified
- **WHEN** an item has no `modified` instant
- **THEN** Atom `<updated>` SHALL equal the publication instant, as before

### Requirement: Feed Image Rendering
When the feed has an `image`, RSS SHALL emit a channel `<image>`, Atom a `<logo>` and
JSON Feed an `icon`.

#### Scenario: Native channel image passed through
- **WHEN** a source feed declares a channel image and is rendered as Atom
- **THEN** the Atom feed SHALL contain `<logo>` with that image URL

### Requirement: Optional Native Entry Ids
When `keep_native_ids` is enabled, RSS `<guid>` and Atom `<id>` SHALL use the item's
`native_id` when it has one, with `isPermaLink="true"` only when the id equals the item
link. The internal `unique_id`, watch identity and delivery de-duplication SHALL NOT
change. The setting SHALL be disabled by default.

#### Scenario: Republished feed keeps publisher guids
- **WHEN** `keep_native_ids` is true and a native RSS item has guid `ep1`
- **THEN** the rendered RSS item SHALL contain `<guid isPermaLink="false">ep1</guid>`

#### Scenario: Default ids
- **WHEN** `keep_native_ids` is false
- **THEN** rendered ids SHALL be the item's `unique_id`, as before
