## 1. Spec analysis
- [x] 1.1 `SpecAnalyzer.candidate_clusters`: merge sibling date groups with the same tag, class and date path into their parent
- [x] 1.2 Item roots by structure in the wrappers and the parent; `_cluster_score` uses them
- [x] 1.3 Items rule as a CSS selector list, guarded (all items matched, ≥ 90% of matches dated); fall back otherwise
- [x] 1.4 Link rule chosen by agreement across item roots for merged groups
- [x] 1.5 `_analyze_active` builds the spec from the merged group

## 2. Diagnostics
- [x] 2.1 `explain` lists candidate groups with the number of groups merged (text, JSON, HTML)

## 3. Corpus and tests
- [x] 3.1 `build_corpus.py`: `grouped` and `grouped-quotes` layouts (ru, en), generated after the existing cases
- [x] 3.2 Unit tests: merged timeline, competing quotes table, different date path not merged, category link first, explain output
- [x] 3.3 `corpus_report.py --json` all 1.0; `pytest`, `ruff check`, `ruff format --check`, `mypy` clean

## 4. Docs
- [x] 4.1 `parsing-specs.md` (grouped listings), `explain.md` (merged groups)
- [x] 4.2 CHANGELOG
