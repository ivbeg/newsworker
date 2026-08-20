---
title: "Undated listings"
description: "Opt-in fallback for news indexes that have no publication dates"
---

# Undated listing fallback

Some news indexes contain stable story cards but no publication date. Enable the
conservative fallback explicitly with `--undated` or `undated_fallback: true`.
It runs only after stronger plugin, bridge, spec, and dynamic strategies return
no items.

Candidates need repeated sibling/card structure and meaningful title/link pairs.
Guards reject navigation, forms, product grids, and generic link collections.
Accepted items keep document order, use stable link/title-derived IDs, set
`pubdate` to null, and report `undated` provenance plus confidence diagnostics.
Tune `undated_min_items` and `undated_min_confidence` only against a labeled
local corpus; lower thresholds increase false positives.

All serializers preserve undated items: date fields are null/empty where the
target format permits them and are not fabricated.
