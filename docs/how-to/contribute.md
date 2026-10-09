---
icon: lucide/heart-handshake
---

# How to contribute

This page walks you through a change to `redsun` itself, from the first idea
to the moment it's merged. You don't need to know the code well to start: a
bug report, or a fix to a confusing sentence in these docs, is a good first
contribution. If you're writing a session or a plugin that uses `redsun`,
start with the [tutorial](../tutorials/first-session.md) instead.

Everything you need is on this page: the rules for using AI tools, the
steps a change goes through, and then a section for each task along the
way, from setting up your environment to making a release.

## Using AI tools

!!! note

    This section is mirrored from the zarr-python AI contribution policy:
    [AI-assisted contributions](https://zarr.readthedocs.io/en/main/contributing/#ai-assisted-contributions),
    adapted to `redsun`.

AI coding tools are increasingly common in open source development. These tools are welcome in `redsun`, but the same standards apply to all contributions regardless of how they were produced: whether written by hand, with AI assistance, or generated entirely by an AI tool.

### You're responsible for your changes

If you submit a pull request, you are responsible for understanding and having fully reviewed the changes. You must be able to explain why each change is correct and how it fits into the project.

### Write your own messages

PR descriptions, issue comments, and review responses must be in your own words. The substance and reasoning must come from you. Using AI to polish grammar or phrasing is fine, but do not paste AI-generated text as comments or review responses.

### Read every line

You must have personally reviewed and understood all changes before submitting. If you used AI to generate code, you are expected to have read it critically and tested it. The PR description should explain the approach and reasoning; do not leave it to reviewers to figure out what the code does and why.

### Keep pull requests small enough to review

Generating code with AI is fast; reviewing it is not. A large diff shifts the burden from the contributor to the reviewer. PRs that cannot be reviewed in reasonable time with reasonable effort may be closed, regardless of their potential usefulness or correctness. Use AI tools not only to write code but to prepare better, more reviewable PRs: well-structured commits, clear descriptions, and minimal scope.

If you are planning a large AI-assisted contribution (e.g., a significant refactor or a new subsystem), **open an issue first** to discuss the scope and approach with maintainers. Maintainers may also request that large changes be broken into smaller, reviewable pieces.

### The same goes for documentation

The same principles apply to documentation. `redsun` has semantics of its own (the order of the build steps, what a session answers in `setup`, how services are launched and stopped, which transport a session speaks) that AI tools frequently get wrong. Do not submit documentation that you haven't carefully read and verified.

## What you need

You need a [GitHub](https://github.com/) account, `git`, and
[`uv`](https://docs.astral.sh/uv/), which installs Python and the project's
dependencies for you.

## From idea to merged change

1. **Say what you want to change.** Open an
   [issue](https://github.com/redsun-acquisition/redsun/issues) that describes
   the bug or the feature. A maintainer answers, and you agree on the change
   before you write it, so none of your work is wasted. A small fix, such as a
   typo, can skip this step. [Issues](#issues) shows how to title one.
2. **Get the code.** Most people can't push to the `redsun` repository
   directly, so first
   [fork it](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo)
   on GitHub and clone your fork. Then follow
   [Setting up your copy](#setting-up-your-copy) once.
3. **Make a branch from `main`.** Name it after the kind of change and what it
   does, such as `fix/log-folder`, `feat/strict-sessions` or `docs/glossary`.
   The first part is the same type your
   [commit messages](#commit-messages) start with.
4. **Make the change, with tests.** Before you push, run
   [the tests](#running-the-tests) and
   [the commit checks](#checks-before-each-commit). A change to the docs alone
   only needs [the docs build](#building-the-docs).
5. **Open a pull request against `main`.** Write its title and description as
   [Pull requests](#pull-requests) describes. Then add a
   [changelog entry](#changelog-entries) for each change a user will notice.
   The changelog check fails until the entry is pushed, which is expected.
   If you're not sure what to write, open the pull request without it and say
   so: a maintainer can add or fix the entry on your branch.
6. **Wait for CI and a review.** CI runs the same checks as `uv run tox` and
   reports the result on the pull request. If a reviewer asks for changes,
   push them to the same branch, and the pull request updates by itself.

If you're stuck at any step, ask in your issue or pull request.

## Setting up your copy

These steps give you a copy of `redsun` you can change and test.

### Get the code

```bash
git clone https://github.com/redsun-acquisition/redsun.git
cd redsun
uv sync
```

If you work from a fork, clone your fork instead.

`uv sync` creates `.venv` and installs `redsun` in it, with the `dev`
[dependency group](https://peps.python.org/pep-0735/). Without `uv`:

```bash
pip install -e . --group dev
```

### Check that everything works

Run every check once:

```bash
uv run tox
```

This runs every check CI runs: lint, type checks against both
[Qt bindings](../explanation/glossary.md#qt-binding), the tests and the docs
build. Each check gets its own environment built from `uv.lock`, so your
result matches CI's. [Running the tests](#running-the-tests) explains each environment.

## Running the tests

Here you run the `redsun` test suite, type-check it against both
[Qt bindings](../explanation/glossary.md#qt-binding), and produce coverage
reports.

### Everything at once

`tox` runs the environments CI runs, each built from `uv.lock`:

```bash
uv run tox
```

That lints, type-checks against both Qt bindings, runs the tests and builds
the docs. Run one environment with `-e`:

```bash
uv run tox -e tests
uv run tox -e mypy-pyqt
```

| environment | what it runs |
| --- | --- |
| `lint` | `prek run --all-files`: the [commit checks](#checks-before-each-commit) |
| `mypy-pyqt` / `mypy-pyside` | `mypy` against that Qt binding |
| `tests` | `pytest -q` |
| `docs` | `zensical build` then the cross-reference check |

### Only some tests

Arguments after `--` go to `pytest`:

```bash
# the tests of the shared modules only
uv run tox -e tests -- tests/sdk/

# a specific test function
uv run tox -e tests -- tests/test_container.py::test_function_name

# everything matching a pattern
uv run tox -e tests -- -k "test_wiring"
```

The project environment skips the sync, so it's faster while editing:

```bash
uv run pytest tests/sdk/ -x
```

Tests marked `@pytest.mark.qt` are skipped when there's no display.

### Tests that need a container

Tests marked `@pytest.mark.compose` talk to an
[IOC](../explanation/glossary.md#ioc) in a container started from
`tests/compose/compose.yaml`. They're skipped unless `REDSUN_COMPOSE` is set,
so the rest of the suite needs no container runtime. With Docker running:

```bash
docker compose -f tests/compose/compose.yaml up --detach --wait
REDSUN_COMPOSE=1 uv run pytest -m compose
docker compose -f tests/compose/compose.yaml down
```

The IOC listens on `127.0.0.1` port 5064, the default
[Channel Access](../explanation/glossary.md#channel-access) port, so stop any
other IOC on that port first. CI runs these tests in their own job on Ubuntu.

### Type checks for both Qt bindings

`mypy` checks the tests in strict mode along with the sources. `redsun`
supports `pyqt6` and `pyside6`, whose type stubs disagree on some signatures,
so both are checked:

```bash
uv run tox -e mypy-pyqt,mypy-pyside
```

Each environment installs only its own binding and sets `QT_API`, which
selects the branches `qtpy` shows the type checker. A green `mypy-pyqt` says
nothing about `mypy-pyside`.

!!! warning "`mypy` in the project environment gives different results"

    The project environment holds both bindings, so `mypy` there reports errors
    neither binding has on its own and can miss errors CI catches. Run the
    `tox` environments instead.

### Coverage report

`pyproject.toml` configures the coverage sources:

```bash
uv run coverage run -m pytest
uv run coverage html
```

Open `htmlcov/index.html` in a browser.

## Checks before each commit

`redsun` checks formatting and lint with [`prek`](https://prek.j178.dev), which
runs the hooks listed in `prek.toml` at the project root. The same hooks run on
every commit once you install them, in `uv run tox -e lint`, and in CI.
`prek` and `ruff` are in the `lint` dependency group, which `dev` includes.

### Turn on the git hook

Once per clone, from the project root:

```bash
uv run prek install
```

This writes `.git/hooks/pre-commit`, so from then on `git commit` runs the hooks
on the staged files and stops the commit if one fails.

### Run the checks by hand

To run every hook on every file, without committing:

```bash
uv run prek run                         # staged files only
uv run prek run --all-files             # every tracked file, as CI does
uv run prek run ruff-check --all-files  # a single hook
```

### What gets checked

| hook | what it does |
| --- | --- |
| `end-of-file-fixer` | ends every file with exactly one newline |
| `trailing-whitespace` | strips spaces at the end of lines |
| `check-yaml`, `check-toml` | fails on files that do not parse |
| `check-added-large-files` | fails on large files added to the index |
| `check-merge-conflict` | fails on leftover conflict markers |
| `ruff-check` | `ruff check --fix` |
| `ruff-format` | `ruff format` |

### When a check fails

A hook that can fix what it found rewrites the file and still reports a
failure, so the commit stops with the fix unstaged. Review the change, stage it
with `git add`, and commit again. If `--fix` can't repair a `ruff` violation,
the hook prints it with its rule code and you fix it by hand.

CI runs `prek run --all-files --show-diff-on-failure`, so a file a hook
rewrites fails the build there and the log shows the diff.

### Which version of `ruff` runs

The `ruff` hooks run `uv run --locked --only-group lint ruff`, so they use the
version pinned in `uv.lock`, the same one `tox` and CI use. When you update `ruff`
in the lock file the hooks follow, because `prek.toml` holds no separate
version for it. `--only-group lint` makes a fresh clone install only `prek` and
`ruff` before the hooks run, and it adds to the project environment without
removing anything from it.

## Building the docs

Here you build the documentation site, check it, and look at it locally while
you write.

### Build and preview the site

From the project root:

```bash
uv run tox -e docs
```

This builds the site, then runs `scripts/check_xrefs.py`, which reports every
cross-reference that resolves to nothing. `zensical build` alone passes with
such references, so prefer the `tox` environment, which also installs what the
docs need from `uv.lock`.

Zensical is in the `docs` dependency group, which `dev` doesn't include, so a
command that runs it directly names the group:

```bash
uv run --group docs zensical build     # build only, no cross-reference check
```

The site lands in `site/`. Serve it locally with:

```bash
uv run --group docs zensical serve
```

The server listens on `http://localhost:8000` and rebuilds on every change.

### Pictures of example windows

A tutorial's code lives in a script next to its page, such as
`docs/tutorials/first_session.py`, and the page pulls each step from it. The
build runs the script and saves a picture of the window it opens:

```bash
uv run --group docs python scripts/screenshots.py
```

`uv run tox -e docs` runs this first. If you serve the site with `zensical
serve`, run it once yourself, or the tutorial shows a missing image. The
pictures are generated, so they aren't in git. The window opens on screen for a
moment and needs a display, which CI provides with a virtual one.

To add a picture, add the script and the image's path to `SCREENSHOTS` in
`scripts/screenshots.py`.

### Common problems

#### `zensical` is not found

`uv run zensical` without `--group docs` fails with
`Failed to spawn: zensical`. Add the flag, or install the group once:

```bash
uv sync --group dev --group docs
```

#### Port already in use

Pick another port:

```bash
uv run --group docs zensical serve --dev-addr localhost:8080
```

## Commit messages and pull requests

Commit messages, issue titles and pull requests all follow one form, so the
history reads the same everywhere.

### Commit messages

The first line follows [Conventional Commits](https://www.conventionalcommits.org):

```
type(scope): summary
```

- `type` is one of `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `chore`.
  Add `!` after it for a change that breaks existing code: `feat!: ...`.
- `scope` is optional and names the part changed: `session`, `qt`, `log`.
- The summary is in the imperative ("add", "fix", "move"), with no full stop,
  and the whole line is 72 characters or fewer.

A commit that does several things gets a body of short bullets, each one
imperative:

```
refactor(session): read each session file once

- merge the sources before validating them
- log the files in the order they are layered
```

Write what changed in plain words, so someone who hasn't seen the diff
understands it.

### Issues

An issue title takes the same form as a commit's first line and names the
change it asks for: `fix: log files stay open after shutdown`,
`feat: add a toolbar placement`. The issue templates start the title for
you.

### Pull requests

Open the pull request against `main`. Its title follows the same rules as a
commit's first line, such as `feat(session): add strict sessions`. The
changelog doesn't use it: what users read comes from the
[changelog entries](#changelog-entries) the pull request adds.

The description is a list of one-line bullets in the imperative, one per
change a reviewer can see, with no headers:

```markdown
- Add `strict` to the session file
- Stop a session whose component fails to build when `strict` is set
- Rename `MyMotor.go` to `MyMotor.move`, which existing code must follow
```

A change that existing code must follow says so in its bullet. Leave out tests,
coverage and the checks you ran: CI reports them on the pull request.

### Changelog entries

Each change a user will notice gets a file in `changelog.d/`, named after the
pull request and the kind of change, such as `412.fixed.md`. Open the pull
request first, so you know its number. A release collects the files into the
[changelog](../reference/changelog.md), one entry each, and links each entry
to its pull request.

| kind | use it when |
| --- | --- |
| `breaking` | code that uses `redsun` has to change |
| `added` | something new: a class, a function, a keyword, a section of the session file |
| `changed` | something that already existed behaves differently |
| `deprecated` | something still works but warns, and goes in a later release |
| `removed` | something is gone |
| `fixed` | something now works as its documentation says |
| `security` | a vulnerability is closed |

`towncrier` writes the file for you. Keep the text in single quotes, so the
shell leaves its backticks alone:

```bash
uv run towncrier create 412.fixed.md --content 'A link that `wire` and `wiring:` both name is made once.'
```

A second change of the same kind in one pull request goes in `412.fixed.2.md`.

An entry says what changed, in a line or two, and names what a user would
type to reach it: a name `redsun` exports as it is, such as `WindowLayout`,
and any other with its module, such as `redsun.aio.run_coro`. It doesn't say why: that belongs in the pull request or in
a [decision record](../explanation/decisions/index.md).

```markdown
Good: Add `timeout=` to `run_coro`, which cancels the coroutine when the wait ends without a result.
Bad:  Improve run_coro.
```

A change to something not released yet gets no entry of its own. Edit the
entry that added it instead, so the release says what users get.

A pull request nobody using `redsun` would notice, such as tests, CI, a
refactor or docs alone, needs no entry. A maintainer gives it the
`skip-changelog` label, and CI accepts it without one.

## Writing documentation

Write for someone new: picture a reader who knows some Python and nothing about
`redsun` or lab hardware, and explain things the way you would in person. Talk
to them as "you", keep most sentences short, and show a small code example
when it says more than a paragraph would. Docstrings count too, because the
API reference is made from them.

### Where a page goes

The docs have four sections, and each page belongs in the one that matches
what its reader wants:

| section | the reader wants to | example |
| --- | --- | --- |
| Tutorials | learn by building something, step by step | build your first session |
| How-to Guides | get one task done | how to write a service |
| Explanations | understand how and why | how a session works, the glossary |
| Reference | look up a fact | an API page, the changelog |

Write each fact once, on the page where it belongs, and link to it from the
others. A wrong API page is fixed in its docstring, not in a `.md` file.

### Headings, terms and wording

Give each section a short heading that names its topic, such as "Devices and
services", so a reader scanning the table of contents finds it. Name it in
the reader's words rather than after the class or mechanism behind it: "A
tree of device settings", not "Descriptor tree view". How-to steps
and tutorial steps are the exception: they say what the reader does, such as
"Declare the device".

The first time a page uses a technical word, link it to its entry in the
[glossary](../explanation/glossary.md):

```markdown
A [layer](../explanation/glossary.md#layer) is built after the one before it.
```

If the glossary doesn't have the word yet, add it there first. Acronyms such
as ADR also go in `includes/abbreviations.md`, which shows them as tooltips on
every page.

Prefer plain words to the jargon of a field: write "can't change without
breaking X" rather than "load-bearing". Leave out em dashes and sales words
such as "powerful", and write arrows as `->`.

If you work on the docs with an AI tool, point it at
`.claude/skills/docs-conventions/SKILL.md`, which holds the full set of rules
these pages follow.

### Code in tutorials

A tutorial takes its code from the script beside it, so the page always shows
code that runs. Mark each part of the script with a `start` and an `end`
comment, and include it as `docs/tutorials/first-session.md` does. Write the
fence of an included part as `{.python}`: inside a `python` fence, `ruff
format` would rewrite the include line, and the page would show that line
instead of the code. End each tutorial with the whole script in a collapsed
block, before "What you built".

The tutorial scripts are type checked with the rest of the code, by
`uv run tox -e mypy-pyqt,mypy-pyside`.

### Checking your changes

```bash
uv run tox -e docs
```

This builds the site, then checks that every cross-reference found its
target, every included script was read, and every link to a part of a page
reaches it. The build alone doesn't fail on any of these, which is why the
check runs after it. See [Building the docs](#building-the-docs).

## Recording a design decision

An [ADR](../explanation/glossary.md#adr) records one decision about how
`redsun` is built, and the reasons for it. The records live in
`docs/explanation/decisions/`.

### When to write one

Write one when a change decides how parts of `redsun` fit together, and a
future contributor would otherwise ask "why is it like this?". Examples are
the order a build runs in, what a component may ask for, or where acquisition
files are written. A bug fix, or a new option that follows an existing
decision, doesn't need one.

### How to write one

1. Copy `docs/explanation/decisions/COPYME` to the next free number, as
   `NNNN-short-title.md`.
2. Fill in the sections: the context, the decision, and its consequences.
   Follow [Writing documentation](#writing-documentation).
3. Add it to the `Decisions` list in `zensical.toml` and to
   `docs/explanation/decisions/index.md`.

### Changing a decision

Don't edit an accepted ADR. Write a new one that replaces it, and set the old
one's status to "Superseded by" with a link to the new one.

## Making a release

A release starts with the changelog, which `towncrier` writes from the entry
files the pull requests added since the last release. Don't edit it by hand,
except to fix an entry while releasing.

### What you need for a release

You need a clone of the repository, and `gh`, the GitHub command-line tool,
signed in with access to it.

### 1. Write the changelog

On an up-to-date `main`, make a release branch and write the section, with
the version without its `v` and today's date:

```bash
git switch main
git pull
git switch -c release/v0.14.1
uv run towncrier build --yes --version 0.14.1 --date 01-10-2026
```

`towncrier` collects the files in `changelog.d/` into a section at the top of
`docs/reference/changelog.md`, deletes them, and stages both changes. `--yes`
deletes them without asking; without it, a "no" leaves them to be collected
again by the next release.

Read the section. If an entry reads badly, fix it in the changelog, which is
now the only copy.

### 2. Merge the changelog

Commit the section, push the branch, and open a pull request for it:

```bash
git commit -am "docs: add the 0.14.1 changelog"
git push origin release/v0.14.1
gh pr create --base main --label skip-changelog \
  --title "docs: add the 0.14.1 changelog" \
  --body "Adds the changelog section for 0.14.1."
```

The checks start as on any pull request. Merge it once they pass.

### 3. Tag the release

Tag the merge commit and push the tag:

```bash
git switch main
git pull
git tag v0.14.1
git push origin v0.14.1
```

The tag publishes the package to PyPI and the docs, and creates the GitHub
release, whose notes are the changelog section.

!!! warning "A final-release tag without a changelog section"

    If the tag's version has no section, the package build fails with a
    message naming the `towncrier build` command, and neither PyPI nor the
    GitHub release gets anything. Merge the changelog pull request (steps 1 and 2)
    before you tag.

### Release candidates

Tag a candidate `v0.14.1rc1` without preparing anything. It publishes the
package, but no GitHub release and no changelog section: the entries stay in
`changelog.d/` until the final release collects them.
