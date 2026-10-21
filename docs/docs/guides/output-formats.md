---
title: "Output formats"
description: "JSON, JSON Feed, RSS, Atom, CSV, HTML, Markdown, YAML, and OPML outputs"
---

# Output formats

## `extract`

| Format | Description |
| --- | --- |
| `json` | The raw internal representation (feed metadata + items). Default. |
| `jsonfeed` | [JSON Feed 1.1](https://jsonfeed.org/version/1.1) document. |
| `rss` | RSS 2.0 document generated with [`feedgen`](https://github.com/lkiesow/python-feedgen). |
| `atom` | Atom 1.0 document generated with `feedgen`. |
| `csv` | Flat table of items: `title, link, pubdate, description, content, content_kind, image, author, categories, unique_id, date_precision`. |
| `html` | A standalone HTML preview page rendering items as cards. |
| `markdown` | A Markdown bulleted list (date, title, link per item). |
| `yaml` | The feed dictionary serialized as YAML (symmetric with the spec format). |

## `scan`

| Format | Description |
| --- | --- |
| `json` | The raw list of discovered feeds. Default. |
| `rss` / `atom` | Each discovered feed becomes an entry (its title and URL). |
| `csv` | Flat table: `title, url, feedtype, num_entries, language, confidence`. |
| `opml` | OPML 2.0 subscription list for importing feeds into readers. |

Publication times in the internal feed dictionary are timezone-aware UTC
`datetime` values. When rendering RSS/Atom they are emitted as UTC (a
requirement of the feed formats). See [migration notes](/guides/migration-1-4)
for `content_kind` and enclosure rules.

## Date precision

Every dated item records how precisely its date is known in `date_precision`:

| Value | Meaning | Examples |
| --- | --- | --- |
| `day` | A calendar day without a time of day. | `5 мая 2022`, `05.05.2022`, `<time datetime="2022-05-05">`, `yesterday`, `3 days ago` |
| `minute` | A time of day to the minute. | `5 May 2022, 12:30`, `2022-05-05T10:00+03:00`, `3 hours ago`, `вчера в 14:30` |
| `second` | A time of day to the second. | `2022-05-05 10:00:30`, RSS `pubDate`, JSON-LD `2022-05-05T10:15:00+03:00` |

A `day` date is the calendar day as printed, stored as 00:00 UTC on that day.
It is not converted from `default_timezone`: "5 May" on a site in UTC+3 stays
5 May instead of becoming 4 May, 21:00 UTC. A relative day ("yesterday") is
the day in `default_timezone`. Times (`minute`, `second`) are instants:
written offsets are honoured, other times are read in `default_timezone`. The
key is absent for undated items and may be absent for plugin items.

How each format carries it:

| Format | Day-precision date | Precision |
| --- | --- | --- |
| `json`, `yaml` | `pubdate` at `T00:00:00+00:00` | `date_precision` key on each item |
| `jsonfeed` | `date_published` at `T00:00:00+00:00` (JSON Feed requires a time) | `"_newsworker": {"date_precision": "day"}` on day items only |
| `rss`, `atom` | `pubDate` / `published` at `00:00:00 +0000` | not represented |
| `csv` | `pubdate` at `T00:00:00+00:00` | `date_precision` column |
| `html`, `markdown` | the date alone (`2022-05-05`) | implied by the shown value |

The day is kept in every output. A feed reader that shows times in its own
time zone may still display a `day` date on the previous day west of UTC;
`date_precision` (or the JSON Feed extension) tells consumers that the
00:00 UTC time is a placeholder. `newsworker explain` prints each item's
precision next to its date.

Undated items keep null/empty date fields where the target format permits them
and are not fabricated. See [undated listings](/guides/undated).
