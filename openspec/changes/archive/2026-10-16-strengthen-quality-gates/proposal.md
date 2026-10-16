# Change: Strengthen engineering quality gates

## Why
The configured lint and type checks pass but cover only narrow rules and two modules,
formatting is not enforced, coverage is 71% with critical modules below 55%, and CI
builds Docker without running it. Packaging and Python support metadata are also inconsistent.

## What Changes
- Enforce Ruff formatting and incrementally ratchet high-signal lint rules.
- Expand type annotations and checked function bodies across public boundaries.
- Add coverage thresholds that rise from 75% to 85% with per-critical-module targets.
- Test optional extras, built-wheel installation, package metadata, and a running Docker image.
- Align declared, classified, linted, typed, and tested Python versions.
- Modernize license/dependency-lock metadata and document the release verification flow.

## Impact
- Affected specs: `quality-gates`
- Affected code: `pyproject.toml`, CI, pre-commit, tests, package typing/metadata,
  Docker smoke configuration, developer docs
- Dependencies: coordinate with the active `improve-dev-quality` change; archive or
  explicitly defer its optional MkDocs task before implementing this proposal

