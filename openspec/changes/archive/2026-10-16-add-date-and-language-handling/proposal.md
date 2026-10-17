# Change: Fuzzy relative dates and language detection

## Why
Two related parsing gaps: many pages use relative dates ("2 hours ago", "yesterday") that
`qddate` does not handle, and the extractor hardcodes `language = "en"` (see the FIXME at
`extractor.py:94`) instead of detecting the page language. (Audit E7, E8, B11.)

## What Changes
- Pre-process fuzzy relative date strings ("yesterday", "N hours/days ago", "just now")
  into absolute datetimes with a small regex set before handing off to `qddate`.
- Detect the feed language from the HTML `lang` attribute and/or the `Content-Language`
  response header, replacing the hardcoded `"en"`.
- Add a `--language LANG` CLI hint (and setting) to override auto-detection.

## Impact
- Affected specs: `feed-extraction`
- Affected code: `extractor.py` (date pre-processing, language detection at ~line 94),
  `tools.py` (fuzzy-date helper), `settings.py`, `core.py`
