# Change: Read listings split into sibling groups as one listing

## Why
Date clustering pairs consecutive dates at the same depth, so a listing that puts
its items into sibling wrappers (one per hour, day or block) becomes one date group
per wrapper, and the wrappers' parent only gets the dates at the wrapper borders.
Spec analysis then picks one small group or a stray table. On interfax.ru
(2026-11-04 snapshots, qddate 1.1.0) the timeline `div.timeline` holds 50 items:
most in `div.timeline__group > div` (one to eight per group), the rest as
`div.timeline__text`, `div.timeline__smalltext` or `div.timeline__photo` directly in
the timeline, each `time[datetime] + a > h3`:

- `/russia/`: 10 of 50 items (only the `timeline__smalltext` ones).
- `/business/`: 9 untitled rows of a finmarket quotes table (`02.11 00:00`): its
  8 dates and 6 links beat every group of two or three items.
- `/` (home): 34 items, 20 of them linked to the home page instead of the article.

## What Changes
- **Grouped listings in spec analysis**: when at least two date groups have
  shared nodes that are siblings with the same tag and class, and their items
  reach the date along the same tag path, `SpecAnalyzer` adds one merged date
  group for their parent. It takes the parent's own date group and replaces the
  sibling groups. It competes with the other groups under the existing score
  (links and titles in the first six items, date count, news-class bonus).
- **Items found by structure**: the merged group's items are the children of
  each wrapper, plus the parent's other children, that hold an element at the
  same date path. Items no date group paired, such as a wrapper with one item,
  count too.
- **Items rule across groups**: a CSS selector list inside the parent, such as
  `div.timeline__group > div, div.timeline__text, div.timeline__smalltext`. It
  must match every item, and at least 90% of the elements it matches must hold
  the date. If not, the merged group is dropped and analysis works as today.
  The spec format does not change.
- **Link rule checked across item kinds**: some items start with a category
  link and others do not, so the link rule must not come from one sample alone.
  Analysis compares the sample's link selector with the link that holds or sits
  inside the title heading (`.//a[.//h3]`, `h3 a`). It keeps the rule that finds
  the article link in more items.
- **explain**: the merged group shows as one date group with its container, its
  date count and the number of wrappers holding items (`in 11 groups` on
  `/russia/`; `groups` in JSON and HTML).
- **Corpus**: `grouped` and `grouped-quotes` layouts (ru, en) modelled on the
  interfax timeline. They are generated after the existing cases, so existing
  pages and seeds do not change.
- Dynamic extraction (`getclusters`, `process_clusters`) is unchanged. It
  already turns every date group into items.

## Impact
- Affected specs: `feed-extraction` (ADDED Grouped Listings),
  `extraction-diagnostics` (MODIFIED Extraction Explanation Report)
- Affected code: `newsworker/spec/analyze.py`, `newsworker/explain.py`,
  `benchmarks/build_corpus.py`, `tests/corpus`, tests, docs (`parsing-specs.md`,
  `explain.md`)
- Behaviour change: pages with sibling date groups of the same class get a
  different spec (more items, other selectors). Specs already in the cache keep
  their rules until they are re-analysed (`--no-cache`, cache expiry, or the
  existing re-analysis of a spec that yields nothing).
- No new dependency, no spec schema change; no corpus page has such groups
  today (checked on all 232 cases with a prototype).
