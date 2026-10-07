---
icon: lucide/pen-line
---

# How to write documentation

These rules apply to every page under `docs/` and to every docstring, since
the reference pages are made from docstrings.

## Write for a reader who is new to this

Picture a reader around 15 years old who knows some Python and nothing about
`redsun` or lab hardware.

Write as if you were explaining it to them in person.

- Talk to the reader as "you". Name who does what: "you declare the device",
  "the session starts the service".
- Start a section with what the reader gets out of it, then explain how.
- Keep most sentences short, but vary their length. Join ideas that belong
  together with "so", "because" or "which means", rather than splitting them
  into a list of short statements.
- Contractions such as "you can't" and "it's" are fine.
- Use the active voice: "the session starts the service", not "the service is
  started".
- Show a short code example when it is clearer than a paragraph.

| stiff | friendly |
| --- | --- |
| A view's class names where it attaches by default. | Each view class has a default place in the window. You can pick another when you declare the view. |
| There is no way to hand the session a new value later. | You can't hand the session a new value after it starts. |
| `redsun` is a library you build an acquisition program with. | `redsun` is a toolkit for building your own acquisition software. |

## Name a section by its topic

A heading names what the section is about, in a few words, so a reader
scanning the table of contents finds it. Put the claim in the first sentence
of the section, not in the heading.

- Use a short noun phrase: "Devices and services", "Unexpected exits".
- A question works on a page of limits or trade-offs: "Can I add a value after
  startup?"
- Use the real name of the thing, not a placeholder such as "part", "role" or
  "aspect".
- A heading is not a sentence: no "cannot" or "must", and no clause such as
  "while the session runs".

How-to guides and tutorials are the exception: their steps are headed with
what the reader does, such as "Declare the device".

## Define each term once

Every technical word, such as session, layer, placement or slot, has one
plain definition in the [glossary](../explanation/glossary.md). A page links
the word to its glossary entry the first time it uses it:

```markdown
A [layer](../explanation/glossary.md#layer) is built after the one before it.
```

Never write a second full definition somewhere else. A few words in passing
are fine when they save the reader a click, as long as the link is there too:

```markdown
The camera reads its signals under the
[prefix](../explanation/glossary.md#prefix) `CAM:`, which starts the name of
each of its process variables.
```

If a word needs explaining and is not in the glossary yet, add it there first.

Acronyms such as ADR also go in `includes/abbreviations.md`, which turns
them into tooltips on every page. Keep that file to acronyms and rare words,
since it underlines every place the word appears.

## Say the thing itself

Write the claim, not a figure of speech for it. "Load-bearing", "footgun",
"first-class" and "plumbing" only make sense to people who already know the
jargon. Write what they stand for: "cannot change without breaking X", "easy
to misuse", "fully supported", "the code that connects X to Y".

This is about words that only one field uses. Everyday phrases that any reader
knows, such as "out of the box" or "behind the scenes", are fine.

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
target, every included script was read, and every link to a part of a page
reaches it. None of the three stops the build on its own, which is why the
check runs after it. See [Build the docs](build-docs.md).
