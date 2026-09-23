# Contributing

This section is for people changing `redsun` itself. If you are writing a
session or a plugin that uses `redsun`, start with the
[tutorial](../tutorials/first-session.md) instead.

## How a change goes in

1. **Open an issue** describing the bug or the feature, so the change is
   agreed on before you write it. A small fix can skip this.
2. **Branch from `main`**, named after the kind of change and what it does:
   `fix/log-folder`, `feat/strict-sessions`, `docs/glossary`.
3. **Set up your environment** once: see [Set up](setup.md).
4. **Make the change**, with tests. Run the checks before you push:
   see [Run tests](run-tests.md) and [Run the commit checks](run-commit-checks.md).
5. **Open a pull request against `main`**, following
   [Commits and pull requests](commits-and-prs.md). Give it the label that
   says which changelog section it belongs in.
6. **Wait for CI and a review.** CI runs the same checks as
   `uv run tox`. A reviewer may ask for changes; push them to the same branch.

## The pages in this section

- [Set up](setup.md): the development environment.
- [Run tests](run-tests.md): the test suite, type checks and coverage.
- [Run the commit checks](run-commit-checks.md): formatting and lint.
- [Build the docs](build-docs.md): the documentation site.
- [Commits and pull requests](commits-and-prs.md): how to write them, and the
  labels.
- [Write documentation](write-docs.md): the writing style.
- [Record a decision](decisions.md): when and how to write an
  [ADR](../reference/glossary.md#adr).
- [Make a release](release.md): how the changelog is written and a version
  published.
