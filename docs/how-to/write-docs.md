---
icon: lucide/pen-line
---

# How to write documentation

These rules apply to every page under `docs/` and to every docstring, since
the reference pages are made from docstrings.

## Write for a reader who is new to this

Picture a reader around 15 years old who knows some Python and nothing about
`redsun` or lab hardware.

- Keep sentences short, with one idea each.
- Use the active voice: "the session starts the service", not "the service is
  started".
- Say what a thing does before saying why.
- Show a short code example when it is clearer than a paragraph.

## Define each term once

Every technical word, such as session, layer, placement or slot, has one
plain definition in the [glossary](../explanation/glossary.md). A page links
the word to its glossary entry the first time it uses it:

```markdown
A [layer](../explanation/glossary.md#layer) is built after the one before it.
```

Never write a second definition somewhere else. If a word needs explaining
and is not in the glossary yet, add it there first.

Acronyms such as ADR also go in `includes/abbreviations.md`, which turns
them into tooltips on every page. Keep that file to acronyms and rare words,
since it underlines every place the word appears.

## Say the thing itself

Write the claim, not a figure of speech for it. "Load-bearing", "footgun",
"first-class" and "plumbing" only make sense to people who already know the
jargon. Write what they stand for: "cannot change without breaking X", "easy
to misuse", "fully supported", "the code that connects X to Y".

Other rules:

- No em dashes or en dashes. Use a hyphen, a comma, or two sentences.
- Write arrows as `->`, not as a special character.
- No sales words ("powerful", "seamless") and no closing summary sentence.

## Put the page in the right section

| section | the reader wants to | example |
| --- | --- | --- |
| Tutorials | learn by building something, step by step | build your first session |
| How-to Guides | get one task done, including contributing and migrating | how to write a service |
| Explanations | understand how and why | how a session build sequence works, the glossary |
| Reference | look up a fact | an API page, the changelog |

Write each fact once, on the page where it belongs, and link to it from the
others. The API reference comes from docstrings, so fix a wrong API page in
the docstring, not in the `.md` file.

## Show the code of a tutorial

A tutorial includes its code from the script beside it, so the page shows
what runs. Mark each part of the script with a `start` and an `end` comment,
and include it as `docs/tutorials/first-session.md` does.

Write the fence of an included part as `{.python}`. `ruff format` reads the
line inside a `python` fence as Python and rewrites it, and the page then
shows that line in place of the code.

End each tutorial with the whole script in a collapsed block, before
"What you learned".

The tutorial scripts are type checked with the rest of the code, by
`uv run tox -e mypy-pyqt,mypy-pyside`.

## Check the build

```bash
uv run tox -e docs
```

This builds the site and then checks that every cross-reference found its
target and every included script was read. Neither a link to a missing
symbol nor a misspelt include stops the build on its own, which is why the
check runs after it. See [Build the docs](build-docs.md).
