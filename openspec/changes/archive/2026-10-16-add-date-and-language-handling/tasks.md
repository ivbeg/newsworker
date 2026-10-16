## 1. Fuzzy dates
- [x] 1.1 Add `parse_fuzzy_date(text, now=None)` in `tools.py` handling "yesterday",
      "today", "just now", "N minutes/hours/days/weeks ago"
- [x] 1.2 Call it in the extractor before `qddate` and use the resolved datetime when matched
- [x] 1.3 Keep resolution relative to fetch time (injectable `now` for tests)

## 2. Language detection
- [x] 2.1 Detect language from `<html lang>` and/or `Content-Language` header
- [x] 2.2 Replace the hardcoded `"en"` (extractor.py:94) with the detected value, defaulting to `en`
- [x] 2.3 Add `--language` CLI option + `default_language` setting override

## 3. Tests & docs
- [x] 3.1 Unit test fuzzy-date resolution with a fixed `now`
- [x] 3.2 Unit test language detection from fixtures and header
- [x] 3.3 Document `--language` in README
