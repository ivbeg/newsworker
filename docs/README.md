# Developer documentation

User-facing docs live in the repository root [`README.md`](../README.md) (install, CLI,
settings, output formats). Spec-driven design lives in [`openspec/`](../openspec/) (change
proposals, requirements, tasks).

This folder holds **supplementary** material only. The old Sphinx/autodoc stubs were
removed — they were stale and duplicated what the README and module docstrings already
cover.

## Recommended stack: MkDocs Material + mkdocstrings

For a small library like `newsworker`, a **Markdown-first static site** beats Sphinx:

| Layer | Tool | Role |
|-------|------|------|
| Guides | [MkDocs](https://www.mkdocs.org/) + [Material](https://squidfunk.github.io/mkdocs-material/) | CLI reference, tutorials, architecture, deploy |
| API reference | [mkdocstrings](https://mkdocstrings.github.io/) | Pull docstrings from `newsworker/*.py` into Markdown |
| Specs | Keep `openspec/` in-repo | Proposals and requirements stay versioned with code |
| Hosting | GitHub Pages or Read the Docs (MkDocs builder) | Free CI publish on tag/main |

### Minimal bootstrap

```bash
pip install mkdocs-material mkdocstrings[python]
```

`mkdocs.yml` (sketch):

```yaml
site_name: newsworker
site_url: https://ivbeg.github.io/newsworker/
repo_url: https://github.com/ivbeg/newsworker
theme:
  name: material
nav:
  - Home: index.md
  - User guide:
      - Quick start: guide/quickstart.md
      - CLI: guide/cli.md
      - Settings: guide/settings.md
  - Developer:
      - Architecture: dev/architecture.md
      - Contributing: dev/contributing.md
      - OpenSpec workflow: dev/openspec.md
  - API:
      - Overview: api/index.md
  - Performance: PERFORMANCE_ANALYSIS.md
plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          paths: [.]
          options:
            docstring_style: google
            show_source: true
markdown_extensions:
  - admonition
  - pymdownx.superfences
  - pymdownx.tabbed:
      alternate_style: true
```

Example API page (`docs/api/index.md`):

```markdown
# API reference

::: newsworker.service.FeedService
::: newsworker.formats.format_feed
::: newsworker.spec.FeedSpec
```

Add to `Makefile`:

```makefile
docs:
	mkdocs serve

docs-build:
	mkdocs build --strict
```

Add a CI job that runs `mkdocs build --strict` on pull requests (after `pip install mkdocs-material mkdocstrings[python]`).

### What to write first

1. **`docs/index.md`** — one paragraph + links to README sections (avoid duplicating the full CLI tables).
2. **`docs/dev/architecture.md`** — module map and data flow (extract → spec → formats); can lift from `openspec/project.md`.
3. **`docs/dev/openspec.md`** — link to `openspec/AGENTS.md` workflow for contributors.
4. **API pages** — only public entry points (`FeedService`, CLI modules, `FeedSpec`, plugins/bridges); skip internal helpers.

### Alternatives (when to pick something else)

- **README-only** — fine while the API surface is small and stable (current state).
- **pdoc** — zero-config HTML from docstrings; good for API-only, weak for guides.
- **Sphinx** — only if you need heavy cross-refs, LaTeX, or an existing RTD Sphinx pipeline.

## Contents of this directory

| File | Description |
|------|-------------|
| [`SPEC.md`](SPEC.md) | YAML parsing spec format, `analyze` pipeline, selector conventions |
| [`PERFORMANCE_ANALYSIS.md`](PERFORMANCE_ANALYSIS.md) | Historical performance notes and profiling ideas |

When MkDocs is adopted, move `PERFORMANCE_ANALYSIS.md` under `nav` as shown above and
add `docs/guide/` and `docs/dev/` as the site grows.
