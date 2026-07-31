---
name: docs-conventions
description: Conventions for writing and updating docs under docs/ - Diataxis structure, ADR recording, and mkdocstrings pitfalls. Use when adding or editing documentation, or when a public API change needs its reference updated.
---

# Docs conventions

- Diataxis under `docs/`: `tutorials/` (learning), `how-to/` (task),
  `explanation/` (rationale), `reference/api/` (mkdocstrings-generated facts).
- One authoritative source per fact; cross-link instead of restating.
- Material-style admonitions (`!!! warning`), mermaid fences for diagrams.
- Reference pages are generated from docstrings: fix the docstring, not the
  `.md`, when reference content is wrong.
- Architectural decisions are recorded as ADRs under
  `docs/explanation/decisions/` (numbered, `COPYME` template - same
  convention as ophyd-async). Architecture changes get a new ADR; superseded
  ADRs are marked, not edited. Wire new ADRs into the `zensical.toml` nav and
  `docs/explanation/index.md`.
- **A green `zensical build` does not mean the docs are correct.** An xref that
  matched nothing is emitted verbatim into the page instead of failing the
  build. Run the guard after every build:

  ```bash
  uv run zensical build
  uv run python scripts/check_xrefs.py
  ```

  It scans the built `site/` for leftover `][target]` outside code blocks. A
  hit is either a typo, a symbol that moved, or a third-party object whose
  inventory is missing from `inventories` in `zensical.toml`. If the project
  genuinely publishes no such object (event-model's `DocumentRouter`, for
  one), write it as a plain code span rather than an xref.
