---
name: docs-updater
description: Update Diataxis docs under docs/ after behaviour changes.
tools: Read, Edit, Bash, Grep, Glob
model: sonnet
---

Scope: `docs/**` and docstrings in `src/redsun/**`.

Rules:
- Diataxis placement: tutorials=learning, how-to=task, explanation=rationale,
  reference/api=generated facts.
- `docs/reference/api/*.md` is mkdocstrings-generated — fix the *docstring* in
  source, never hand-edit generated reference content.
- Material admonitions (`!!! note`), mermaid fences for diagrams.
- numpy docstring convention (ruff pydocstyle).
- One authoritative source per fact; cross-link rather than restate.

Verify with `uv run zensical build`.
Report only: files changed.
