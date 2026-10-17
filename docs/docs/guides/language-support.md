---
title: "Language support"
description: "Evidence-based matrix for date parsing, metadata, text detection, and extraction"
---

# Language support matrix

Support labels are evidence-based and split across date parsing, HTML/header
metadata, text/script detection, and end-to-end extraction. A language is called
**supported** only when its committed date fixture and listing behavior pass.
**Partial** means metadata or text detection exists but the qddate date corpus
is not sufficient.

| Language | Date | Metadata | Text | Extraction |
| --- | --- | --- | --- | --- |
| English, French, German, Italian, Portuguese, Russian, Spanish, Ukrainian | tested | tested | tested | supported |
| Bulgarian, Czech | incomplete upstream patterns | tested | partial | partial |
| Arabic, Chinese, Greek, Hebrew, Hindi, Japanese, Korean, Thai | unsupported | tested | tested by script | partial |

The source of truth is `newsworker.language.LANGUAGE_SUPPORT`; localized date
examples are in `tests/fixtures/languages/matrix.json`, and the extraction
corpus (`tests/corpus`) covers listing layouts, absolute and relative dates in
all eight supported languages. newsworker requires qddate 1.0.16 or newer.
General-purpose missing date patterns belong upstream in qddate rather than in
a second newsworker date engine. newsworker only reshapes short date lines that
qddate cannot read as written: a leading dateline place or weekday is dropped
and a day span keeps its first day, so `GENEVA, 21-22 July 2022` reads as
21 July 2022 and `Monday, January 31, 2022` as 31 January 2022.

An explicit `--language` override wins over every automatic signal. With
diagnostics enabled, automatic selection reports `automatic_evidence`,
`ambiguous_evidence`, or `default_fallback` instead of silently implying
certainty.
