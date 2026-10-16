## 1. Specification
- [x] 1.1 Describe the shipped behaviour as spec deltas
- [x] 1.2 Validate with `openspec validate add-roadmap-capabilities --strict`

## 2. Implementation (delivered on the roadmap branches)
- [x] 2.1 Native feeds and structured data (`native.py`, `structured.py`)
- [x] 2.2 Date plausibility and relative dates (`dates.py`, `relative.py`)
- [x] 2.3 Connect-time address checks, header stripping, per-host pacing (`fetch.py`)
- [x] 2.4 Signed feed links and `feed-url` (`server.py`)
- [x] 2.5 Slack, Discord and Matrix channels (`delivery.py`)
- [x] 2.6 Multi-source watch, item history, `history` command (`watching.py`, `dedup.py`)
- [x] 2.7 `explain` command (`explain.py`)
- [x] 2.8 Extraction corpus and network smoke check (`evaluation.py`, `benchmarks/`)
- [x] 2.9 Release workflow (`.github/workflows/release.yml`)
- [x] 2.10 MCP server (`mcp_server.py`)
