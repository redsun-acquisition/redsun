---
icon: lucide/heart-handshake
---

# How to contribute

These steps are for people changing `redsun` itself. If you are writing a
session or a plugin that uses `redsun`, start with the
[tutorial](../tutorials/first-session.md) instead.

## How a change goes in

1. **Open an issue** describing the bug or the feature, so the change is
   agreed on before you write it. A small fix can skip this.
2. **Branch from `main`**, named after the kind of change and what it does:
   `fix/log-folder`, `feat/strict-sessions`, `docs/glossary`.
3. **Set up your environment** once: see [How to set up a development environment](set-up-development.md).
4. **Make the change**, with tests. Run the checks before you push:
   see [Run tests](run-tests.md) and [Run the commit checks](run-commit-checks.md).
5. **Open a pull request against `main`**, following
   [Commits and pull requests](commits-and-prs.md). Give it the label that
   says which changelog section it belongs in.
6. **Wait for CI and a review.** CI runs the same checks as
   `uv run tox`. A reviewer may ask for changes; push them to the same branch.

## The guides for each step

- [How to set up a development environment](set-up-development.md)
- [How to run the tests](run-tests.md)
- [How to run the commit checks](run-commit-checks.md)
- [How to build the docs](build-docs.md)
- [How to write commits and pull requests](commits-and-prs.md)
- [How to write documentation](write-docs.md)
- [How to record a decision](record-a-decision.md)
- [How to make a release](make-a-release.md)
