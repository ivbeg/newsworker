---
title: "OpenSpec"
description: "Spec-driven change proposals for newsworker contributors"
---

# OpenSpec workflow

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) for
spec-driven development. Change proposals, requirements, and tasks live under
`openspec/` in the repository.

Always consult `openspec/AGENTS.md` when:

- Planning new features or breaking changes
- Making architectural changes
- A request mentions "proposal", "spec", "change", or "plan"

Quick commands:

```bash
openspec list
openspec list --specs
openspec validate --strict
```

Do not start implementation of a new capability until the proposal is reviewed.
The in-repo source of truth after merge is `openspec/specs/`.
