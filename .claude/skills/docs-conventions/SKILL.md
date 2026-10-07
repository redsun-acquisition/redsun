---
name: docs-conventions
description: Conventions for writing and updating docs under docs/ - Diataxis structure, ADR recording, and mkdocstrings pitfalls. Use when adding or editing documentation, or when a public API change needs its reference updated.
---

# Docs conventions

- Diataxis under `docs/`: `tutorials/` (learning), `how-to/` (task),
  `explanation/` (rationale), `reference/api/` (mkdocstrings-generated facts).
- One authoritative source per fact; cross-link instead of restating. A
  sentence of recap next to the link is fine when the page cannot be followed
  without it.
- Voice, headings and terms: the section below. The contributing page has
  a short version for people; this skill holds the full rules.
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

## Voice, headings and terms

Write for a reader around 15 years old who knows some Python and nothing about
`redsun` or lab hardware, as if explaining in person. Use the
`writing-with-flow` skill for how sentences and paragraphs connect.

- Talk to the reader as "you"; name who does what ("you declare the device",
  "the session starts the service"). The project promising future work is
  "we": "We will provide tutorials on this in the future".
- Open each section and each paragraph with its point, framed as what the
  reader gets. Start a sentence from what the reader already knows, end it on
  the new part; keep one subject per paragraph.
- Say each point once: no paragraph repeats its section's first sentence, and
  none opens with a label ("The devices are the model") before saying what
  the thing does.
- Most sentences short, lengths varied; join related ideas with "so",
  "because", "which means". Contractions are fine. Active voice.
- A catch the reader can run into goes in a `!!! warning` box: the title names
  what goes wrong, the last sentence says what to do.
- Show a short code example when it is clearer than a paragraph.

| stiff | friendly |
| --- | --- |
| A view's class names where it attaches by default. | Each view class has a default place in the window. You can pick another when you declare the view. |
| There is no way to hand the session a new value later. | You can't hand the session a new value after it starts. |
| `redsun` is a library you build an acquisition program with. | `redsun` is a toolkit for building your own acquisition software. |

Headings name the topic in a few words ("Devices and services", "Unexpected
exits"); a question works on a page of limits ("Can I add a value after
startup?"). The claim goes in the section's first sentence. Use the real name
of the thing, never "part", "role" or "aspect"; no sentences, no "cannot" or
"must", no "while ..." clauses. How-to and tutorial steps say what the reader
does ("Declare the device").

Each technical word has one definition, in `docs/explanation/glossary.md`; link
it on its first use on a page. A few words in passing next to the link are
fine; a second full definition is not. Add a missing term to the glossary
first. Acronyms and rare words also go in `includes/abbreviations.md`.

Write the claim, not a field's jargon ("can't change without breaking X", not
"load-bearing"); everyday idioms any reader knows are fine. No em or en
dashes, arrows as `->`, no sales words, no closing summary sentence.

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
- After a block, say what it does and why the reader needs it, in a few
  sentences. Leave the full explanation to the explanation page and link it.
- Pictures come from `scripts/screenshots.py`, run by the docs build.

## Guides with more than one block of code

The whole code lives in `docs/examples/*.py`, which the page cuts with
snippet markers and closes with, collapsed. `mypy` checks the script, and
`tests/test_doc_examples.py` builds its `MyApp`, mocked and strict; add the
module to its list.
