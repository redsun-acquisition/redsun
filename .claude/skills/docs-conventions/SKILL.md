---
name: docs-conventions
description: Conventions for writing and updating docs under docs/ - Diataxis structure, ADR recording, and mkdocstrings pitfalls. Use when adding or editing documentation, or when a public API change needs its reference updated.
---

# Docs conventions

- Diataxis under `docs/`: `tutorials/` (learning), `how-to/` (task),
  `explanation/` (rationale), `reference/api/` (mkdocstrings-generated facts).
- One authoritative source per fact; cross-link instead of restating.
- Writing style and glossary linking: `docs/how-to/write-docs.md`.
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
  uv run --group docs zensical build
  uv run python scripts/check_xrefs.py
  ```

  It also reports a snippet marker the build left unread. Write the fence of
  a `--8<--` include as `{.python}`, never `python`: `ruff format` rewrites
  the marker inside a `python` fence and the page shows it in place of the
  code.

  It scans the built `site/` for leftover `][target]` outside code blocks. A
  hit is either a typo, a symbol that moved, or a third-party object whose
  inventory is missing from `inventories` in `zensical.toml`. If the project
  genuinely publishes no such object (event-model's `DocumentRouter`, for
  one), write it as a plain code span rather than an xref.

## Tutorials

- One growing application: from the second tutorial on, the reader works in
  `first_session.py`, and each page only adds to it. A change is a marked
  one-line edit (`hl_lines`), never a replaced block.
- One path: a `uv` project (`uv init --bare --pin-python --python 3.11`),
  `uv add`, `uv run`. Choices of tool and extras live in
  `docs/how-to/install-redsun.md`.
- Code is cut from the type-checked scripts in `docs/tutorials/` with snippet
  markers, so a page cannot drift from what runs. No block shows part of a
  class under its class line: show the changed line, or the lines to add.
  The whole script closes the page, collapsed.
- Imports are given as lines to add, below the ones the file has; the
  `from __future__` line stays first.
- Each page: "Before you start" with a "What you need" note, numbered steps,
  a window the reader can see early, "What you built" saying what the reader
  built, and "Next steps". No time estimates.
- A few sentences after a block, not paragraphs of explanation: link the
  explanation page instead.
- Pictures come from `scripts/screenshots.py`, run by the docs build.

## Guides with more than one block of code

The whole code lives in `docs/examples/*.py`, which the page cuts with
snippet markers and closes with, collapsed. `mypy` checks the script, and
`tests/test_doc_examples.py` builds its `MyApp`, mocked and strict; add the
module to its list.
