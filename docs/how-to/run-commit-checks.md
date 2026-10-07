---
icon: lucide/check-check
---

# How to run the commit checks

`redsun` checks formatting and lint with [`prek`](https://prek.j178.dev), which
runs the hooks listed in `prek.toml` at the project root. The same hooks run on
every commit once you install them, in `uv run tox -e lint`, and in CI.

## Prerequisites

[Set up a development environment](set-up-development.md).
`prek` and `ruff` are in the `lint` dependency group, which `dev` includes.

## Install the git hook

Once per clone, from the project root:

```bash
uv run prek install
```

This writes `.git/hooks/pre-commit`, so from then on `git commit` runs the hooks
on the staged files and stops the commit if one fails.

## Run the hooks by hand

```bash
uv run prek run                         # staged files only
uv run prek run --all-files             # every tracked file, as CI does
uv run prek run ruff-check --all-files  # a single hook
```

## What the hooks check

| hook | what it does |
| --- | --- |
| `end-of-file-fixer` | ends every file with exactly one newline |
| `trailing-whitespace` | strips spaces at the end of lines |
| `check-yaml`, `check-toml` | fails on files that do not parse |
| `check-added-large-files` | fails on large files added to the index |
| `check-merge-conflict` | fails on leftover conflict markers |
| `ruff-check` | `ruff check --fix` |
| `ruff-format` | `ruff format` |

## When a hook fails

A hook that can fix what it found rewrites the file and still reports a
failure, so the commit stops with the fix unstaged. Review the change, stage it
with `git add`, and commit again. If `--fix` can't repair a `ruff` violation,
the hook prints it with its rule code and you fix it by hand.

CI runs `prek run --all-files --show-diff-on-failure`, so a file a hook
rewrites fails the build there and the log shows the diff.

## Which `ruff` runs

The `ruff` hooks run `uv run --locked --only-group lint ruff`, so they use the
version pinned in `uv.lock`, the same one `tox` and CI use. When you update `ruff`
in the lock file the hooks follow, because `prek.toml` holds no separate
version for it. `--only-group lint` makes a fresh clone install only `prek` and
`ruff` before the hooks run, and it adds to the project environment without
removing anything from it.

## Next steps

- [Run tests](run-tests.md)
