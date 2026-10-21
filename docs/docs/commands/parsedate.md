---
title: "parsedate"
description: "newsworker parsedate command reference"
---

# `parsedate`

Shows how extraction reads one date string: the same path a date on a page
takes in `extract`, from the [qddate](https://github.com/ivbeg/qddate) pattern
to the UTC time stored in the item.

```bash
newsworker parsedate "18/06/2018"
newsworker parsedate "05/06/2022" --language en-US
newsworker parsedate "5 мая 2022, 12:30" --timezone Europe/Moscow --json
newsworker parsedate "3 hours ago" --now 2022-05-06T12:00:00+00:00
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--json` | | `false` | Print the reading as a JSON object. |
| `--now` | | current time | Reference time (ISO 8601) for relative dates and the plausibility check. Without an offset it is read in the time zone below. |
| `--timezone` | | `default_timezone` setting | IANA time zone for times printed without an offset. |
| `--language` | | `default_language` setting | Page language tag, such as `ru` or `en-US`. |
| `--config` | `-c` | `~/.newsworker/config.yaml` | Settings file for the defaults above. |
| `--verbose` | `-v` | `false` | Debug logging; print a traceback when reading fails. |

The text goes through `FeedExtractor.read_text`, like every date node:

1. **Page language first.** With `--language` the language's patterns and the
   numeric patterns are tried first, then all languages for text with letters
   (see [language support](/guides/language-support#page-language-and-dates)).
2. **Datelines and day spans.** `GENEVA, 29 July 2022` is read as
   `29 July 2022`, `21-22 July 2022` as `21 July 2022`.
3. **Relative dates.** `3 hours ago`, `вчера в 14:30` and the other relative
   forms are resolved against `--now`.
4. **Day/month order.** An ambiguous numeric date is read the way a group of
   such dates would be: month first for `en-US`, day first otherwise
   (see [day and month order](/guides/language-support#day-and-month-order)).
5. **Offset and precision.** A written offset wins over `--timezone`; a date
   without a time is a calendar day, kept as 00:00 UTC
   (see [date precision](/guides/output-formats#date-precision)).
6. **Plausibility.** Dates before 1970 or more than a year after `--now` are
   rejected.

Text output:

```text
text:      05/06/2022
pattern:   dt:date:date_usa (numeric)
parser:    en
order:     mdy, read again (ambiguous dates, page locale en-US)
precision: day
offset:    none: a calendar day is kept as 00:00 UTC
utc:       2022-05-06T00:00:00+00:00
```

`pattern` is the qddate pattern key with the language of its words
(`numeric` for patterns without words); `parser` is the qddate language whose
patterns read it (`all` when the parser for every language did). `--json`
prints the same facts as fields: `text`, `matched`, `now`, `timezone`,
`language`, `source` (`qddate` or `relative`), `pattern`, `matched_text`,
`pattern_language`, `parser_language`, `page_language`, `values` (the qddate
fields), `order`, `order_reason`, `reordered`, `precision`, `offset`,
`offset_source` (`text` or `timezone`) and `utc`.

A text that is not a date prints `No date found in '…'` (or
`{"matched": false, …}` with `--json`) and exits with code 1. To see how the
dates of a whole page were read, use [`newsworker explain`](/commands/explain).
