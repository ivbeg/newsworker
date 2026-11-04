## ADDED Requirements
### Requirement: Grouped Listings
Some listings put their items into sibling wrappers that share a tag and class
(one wrapper per hour, day or block), and the items in all wrappers reach their
date along the same tag path. Spec analysis SHALL read such wrappers as one
listing under their common parent. Items with the same structure placed directly
in that parent SHALL belong to the listing. The inferred spec SHALL select the
items of every wrapper and of the parent, and SHALL give each item its own title
and article link. When analysis cannot build an items rule that matches all of
these items with at least nine in ten of its matches dated, it SHALL behave as
for an ungrouped page.

#### Scenario: Timeline in hourly groups
- **WHEN** a timeline holds 50 dated items, most in `timeline__group` wrappers of one to eight items and the rest as single items between the wrappers
- **THEN** the feed SHALL contain all 50 items, each with its headline as title and its article link

#### Scenario: Table with more dates per group
- **WHEN** the same page also has a quotes table with eight dated rows of short instrument links, and no timeline wrapper holds more than three items
- **THEN** the feed SHALL contain the timeline items and no table rows

#### Scenario: Category link before the headline
- **WHEN** some items of a grouped listing start with a category link and the headline link follows, and other items have only the headline link
- **THEN** every item's link SHALL be its headline link

#### Scenario: Wrappers with different item structure
- **WHEN** two sibling wrappers share a tag and class but the date sits at a different place in their items
- **THEN** they SHALL be scored as separate date groups, as before this change

#### Scenario: Listing without groups
- **WHEN** no two sibling date groups share a tag and class
- **THEN** the chosen date group and the inferred spec SHALL be the same as before this change
