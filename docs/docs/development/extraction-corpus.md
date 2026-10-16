---
title: "Extraction corpus"
description: "Offline quality gate for news detection, link choice and date parsing"
---

# Extraction corpus

`tests/corpus` holds labelled news listing pages. Each case records the items a
person would pick from the page (title, link, date). `tests/test_corpus.py`
runs the default `FeedService` pipeline over every page and fails when quality
drops, so changes to the heuristics are measured instead of guessed.

| What | Where |
| --- | --- |
| Cases and expectations | `tests/corpus/cases.json` |
| Pages | `tests/corpus/pages/*.html` |
| Generator | `benchmarks/build_corpus.py` |
| Report | `python benchmarks/corpus_report.py` |
| Scoring | `newsworker.evaluation` |

The corpus covers 8 languages (en, ru, de, fr, es, it, pt, uk), their common
date styles, and layouts taken from real CMS output: WordPress, Drupal views,
Bootstrap cards, tables, plain lists, date after title, sidebars and pagers that
also carry dates, a category link before the headline, "read more" links, date
plus clock time, flat listings with no wrapper per item, relative dates
("3 hours ago", "вчера"), press-release datelines and day spans
("GENEVA, 21-22 July 2025"), weekday-led US dates ("Monday, July 28, 2025"),
and pages whose dates exist only in JSON-LD or microdata.

Items are matched by link. The report gives precision and recall of items, and
the share of matched items whose title and date are right. The gate requires
every case to be extracted exactly: precision, recall, title and date
accuracy are all 1.00.

Real site snapshots are not committed: their content is third-party copyright.
`benchmarks/live_check.py` checks a few public pages weekly instead
(`network-smoke` job), and new failure patterns found there become new layouts
in the generator.

## Adding a case

1. Add a layout function to `benchmarks/build_corpus.py` reproducing the
   structure (not the text) of the page that fails.
2. Run `python benchmarks/build_corpus.py`, then `python benchmarks/corpus_report.py`.
3. Fix the extractor until the new cases pass without lowering other scores.

## Scoring your own pages

```python
from newsworker.evaluation import CorpusScore, score_case

score = score_case("my-site", feed["items"], [
    {"title": "Budget approved", "link": "https://example.org/n/1", "date": "2025-10-16"},
])
print(score.precision, score.recall)
print(CorpusScore([score]).to_markdown())
```
