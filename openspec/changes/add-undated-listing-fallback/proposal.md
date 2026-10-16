# Change: Add an undated listing extraction fallback

## Why
The date-clustering algorithm cannot extract repeated news cards that publish titles and
links without dates. A separately identifiable, confidence-scored fallback can cover
that limitation without inventing publication times or weakening the default dated path.

## What Changes
- Detect repeated sibling/card structures containing useful title/link fields without dates.
- Run the fallback only after dated/spec/plugin/bridge strategies fail and under explicit policy.
- Emit `pubdate: null` and undated provenance; never synthesize a publication date.
- Score structural consistency and require configurable minimum item/quality thresholds.
- Add false-positive guards for navigation, forms, product grids, and generic link lists.

## Impact
- Affected specs: `undated-extraction`
- Affected code: extraction strategy/service, diagnostics/confidence, CLI/settings,
  renderers, corpus/tests/docs
- Dependencies: `add-extraction-diagnostics` should land first; renderer contracts must
  continue to tolerate null publication dates

