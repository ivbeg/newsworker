## 1. Page language first
- [x] 1.1 Per-thread qddate parser per language (`thread_date_parser(language)`), with numeric patterns
- [x] 1.2 `ExtractionContext` keeps the page date language, the parser order and pattern sessions
- [x] 1.3 `FeedExtractor.match_text` tries the page language, then all languages for text with letters
- [x] 1.4 qddate results remembered per build, also across pattern restrictions
- [x] 1.5 Dynamic extraction, spec analysis and spec extraction set the page language
- [x] 1.6 Tests, language-support guide and CHANGELOG

## 2. Day/month order
- [x] 2.1 `DateReading`, `numeric_order`, `choose_date_order` in `dates.py`
- [x] 2.2 Page locale as written (`detect_page_locale`, `Content-Language`) kept on the context
- [x] 2.3 Clusters choose an order and re-read ambiguous dates; item blocks use it
- [x] 2.4 Spec extraction chooses an order over all item scopes first
- [x] 2.5 `explain` (text, JSON, HTML) and diagnostics show the order and reason
- [x] 2.6 Tests, language-support guide, explain page and CHANGELOG

## 3. Date precision
- [x] 3.1 `match_precision`, `clock_precision`, `anchor_day`, `read_datetime_attr` in `dates.py`; `read_relative`
- [x] 3.2 Day-precision qddate, `<time datetime>`, relative, JSON-LD and JSON Feed dates anchored at 00:00 UTC
- [x] 3.3 `date_precision` on items from dynamic, spec, structured and native strategies; `Item` model
- [x] 3.4 Structured data sharpens a calendar day by precision and in `default_timezone`
- [x] 3.5 JSON/YAML key, CSV column, JSON Feed extension, preview dates, fingerprint, MCP, `explain`
- [x] 3.6 Tests, output-formats guide, README, settings reference and CHANGELOG
