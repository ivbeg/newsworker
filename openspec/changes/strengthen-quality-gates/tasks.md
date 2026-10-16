## 1. Formatting and linting
- [ ] 1.1 Apply Ruff formatting in an isolated mechanical commit
- [x] 1.2 Add `ruff format --check` to CI and align CI/pre-commit Ruff versions
- [x] 1.3 Enable `I`, `B`, and selected `UP`, `SIM`, and `RUF` rules in staged commits

## 2. Types and contracts
- [x] 2.1 Type feed/item, fetch, spec, plugin, and renderer public boundaries
- [x] 2.2 Enable `check_untyped_defs` and expand checked modules incrementally
- [x] 2.3 Add `py.typed` only after the supported public API is typed

## 3. Tests and coverage
- [x] 3.1 Add coverage to the dev extra and CI reports
- [x] 3.2 Set an initial 75% overall gate and per-module targets for critical paths
- [x] 3.3 Ratchet overall coverage to 85% and critical modules to 80%
- [x] 3.4 Add optional-extra and scheduled network smoke jobs

## 4. Packaging and runtime verification
- [x] 4.1 Align the supported Python range across metadata, tools, CI, and docs
- [x] 4.2 Update SPDX license metadata and direct dependency names/bounds
- [x] 4.3 Define a transitive lock/constraints generation workflow
- [x] 4.4 Build, run `twine check`, install the wheel cleanly, and smoke-test CLI/package data
- [x] 4.5 Run the Docker image and probe `/health` in CI

## 5. Documentation
- [x] 5.1 Document local commands matching every CI gate
- [x] 5.2 Document release artifact and dependency-lock verification
- [x] 5.3 Run the complete updated quality pipeline
