# mcp-server Specification

## Purpose
Expose newsworker to AI assistants as read-only Model Context Protocol tools that share the CLI fetch policy.

## Requirements
### Requirement: MCP Tools
`newsworker mcp` SHALL run a Model Context Protocol server over stdio (with the
`mcp` extra) exposing read-only tools `extract_news`, `find_feeds` and
`explain_page`. Every tool fetch SHALL use the same fetch policy as the CLI, and
`extract_news` SHALL return at most 100 items with truncated descriptions.

#### Scenario: Assistant asks for latest news
- **WHEN** a client calls `extract_news` with a news page URL and `limit` 500
- **THEN** the result SHALL contain at most 100 items, newest first, as JSON data

#### Scenario: Extra not installed
- **WHEN** `newsworker mcp` runs without the `mcp` extra
- **THEN** the command SHALL exit with a message naming `pip install 'newsworker[mcp]'`

