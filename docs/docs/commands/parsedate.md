---
title: "parsedate"
description: "newsworker parsedate command reference"
---

# `parsedate`

A debugging helper that shows how [qddate](https://github.com/ivbeg/qddate)
interprets a date string.

```bash
newsworker parsedate "18/06/2018"
```

Add `--verbose` / `-v` to print a traceback when parsing fails. The output is
the raw qddate match: the pattern key, the matched values and the parsed date.
Dates that newsworker reads only after removing a leading place or weekday
(`GENEVA, 29 July 2022`) are not reshaped here; use `newsworker explain` to see
how a page's dates were read.
