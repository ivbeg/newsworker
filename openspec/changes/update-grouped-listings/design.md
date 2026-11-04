## Context
`FeedExtractor.getclusters` pairs each date node with the previous one at the same
depth and files the pair under their shared node. A wrapper per hour or day
therefore yields one date group per wrapper. The parent holding the wrappers only
gets the pairs that cross a wrapper border, or pairs of items placed directly in it.
`SpecAnalyzer` picks one date group, takes the direct children of its shared node as
item roots and builds the items and field rules from them. That rule can describe
one wrapper or one kind of direct item, never the whole listing.

## Goals / Non-Goals
- Goals: one spec that selects every item of a grouped listing, with titles and
  article links. A table or block with more dates per group must not win over it.
  Explanations must show the merged group.
- Non-Goals: nested grouping (day > hour > item), listings whose wrappers have
  different classes, items whose only date is a group heading (a time per item
  with the day in the heading), and changes to dynamic extraction.

## Decisions
- **Merge in `SpecAnalyzer`, not in `getclusters`.** `process_clusters` builds item
  blocks from the direct children of each shared node and already turns every
  date group into items, so a merged group there would duplicate items and break
  block sizing. Spec analysis and `explain` call one
  `SpecAnalyzer.candidate_clusters(clusters)`; `getclusters` output is unchanged.
- **Merge rule**: shared nodes that are siblings (one parent) with the same tag and
  class attribute, at least two of them, and one date path (the tag path from item
  root to date node) for their items. The parent's own date group (border pairs,
  direct items) joins the merged group. Item roots: a child of a wrapper, or a
  direct child of the parent that is not a wrapper, holding an element at that
  date path. Every child is checked by structure, not only the dates that
  clustering paired. A wrapper with a single item, or a direct item between two
  wrappers, never gets a date group of its own.
- **Items rule as a CSS selector list** (`G > item, direct-kind-1, …`) in the parent
  container. It uses the existing `ItemsRule` and selectors, so cached specs,
  `validate-spec` and bridges need no change, and lxml returns the matches in
  document order. Guard: every item root matched, and at least 90% of matches hold
  the date selector. A kind without a class (a bare `div` straight under the
  parent) matches nested elements and fails the guard. Analysis then falls back
  to the current behaviour instead of guessing.
- **Score**: the existing tuple on the merged item roots. Links and titles count
  only in the first six items, so a 50-item timeline and an 8-row quotes table tie
  on links. Titles then decide (the instruments' short names are not titles), and
  the date count after that.
- **Link rule agreement** only for merged groups: the candidates are the sample's
  selector and title-anchored selectors. Each is scored by how many item roots it
  resolves to the link `pick_link_node` chooses there. Flat listings keep today's
  rule, so the change cannot affect them.

## Alternatives considered
- Date-anchored XPath items (`.//time/..`): short, but it also selects every
  other element holding a `time` (an "updated" stamp, ads). It is also unclear
  for date paths deeper than one level.
- New `ItemsRule.group: "nested"` mode: needs a schema change and execution code
  for what a selector list already expresses.
- Merging in `getclusters`: changes dynamic extraction and the cluster debug data
  for little gain (see above).

## Risks / Trade-offs
- Two sibling blocks of one class with identical items (for example "News" and
  "Press releases" side by side under one parent) now become one feed. The
  same-class, same-date-path rule keeps this narrow. The merged feed is still a
  feed of dated news, and no corpus layout has such a case today.
- The selector list grows with each direct item kind (up to five on interfax).
  It stays readable and is validated against the page.

## Migration Plan
None. Cached specs keep working; a re-analysis produces the new rule.
