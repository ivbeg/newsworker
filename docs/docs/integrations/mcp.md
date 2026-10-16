---
title: "MCP server"
description: "Use newsworker as tools for AI assistants over the Model Context Protocol"
---

# MCP server

`newsworker mcp` runs a [Model Context Protocol](https://modelcontextprotocol.io)
server on stdio, so AI assistants and IDEs can read news from any site,
including sites without RSS.

```bash
pip install 'newsworker[mcp]'
```

Register it with an MCP client, for example in a JSON client configuration:

```json
{
  "mcpServers": {
    "newsworker": {"command": "newsworker", "args": ["mcp"]}
  }
}
```

| Tool | Returns |
| --- | --- |
| `extract_news(url, limit=20)` | Latest items of a page or feed, newest first: title, link, published (ISO 8601), description (≤ 500 characters), author, categories; plus the strategy, confidence and warnings |
| `find_feeds(url)` | Feeds the page advertises, verified: title, URL, type, entry count, language |
| `explain_page(url)` | The `explain` text report: date groups, chosen strategy, items, hints |

All tools are read-only (`readOnlyHint`) and fetch through the same policy as
the CLI: robots.txt, private-address blocking, per-host pacing, size limits
and caches. Pass `--config` to use a settings file (user agent, caches,
languages, allowed hosts).
