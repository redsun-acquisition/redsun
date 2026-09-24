---
icon: lucide/scale
---

# How to record a decision

An [ADR](../reference/glossary.md#adr) records one decision about how
`redsun` is built, and the reasons for it. The records live in
`docs/explanation/decisions/`.

## When to write one

Write one when a change decides how parts of `redsun` fit together, and a
future contributor would otherwise ask "why is it like this?". For example:
the order a build runs in, what a component may ask for, or where acquisition
files are written.

A bug fix or a new option that follows an existing decision does not need one.

## How to write one

1. Copy `docs/explanation/decisions/COPYME` to the next free number:
   `0018-short-title.md`.
2. Fill in the sections: the context, the decision, and its consequences.
   Follow [Write documentation](write-docs.md).
3. Add it to the `Decisions` list in `zensical.toml` and to
   `docs/explanation/index.md`.

## Changing a decision

An accepted ADR is never edited. Write a new one that replaces it, and set
the old one's status to "Superseded by" with a link to the new one.
