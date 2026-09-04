---
allowed-tools: Bash(uv:*)
description: Run the full local validation suite
---

`uv run tox` runs every environment: `lint`, `mypy-pyqt`, `mypy-pyside`,
`tests`, `docs`. Run that, then report a one-line result per environment.

On failure, show the failing output, fix it, and re-run only that environment
with `uv run tox -e <name>`.

Both mypy environments must be clean. They install different Qt bindings from
`uv.lock`, and the two disagree on some signatures, so a green `mypy-pyqt` says
nothing about `mypy-pyside`.

`uv run mypy` against the project `.venv` is not a substitute: it holds both
bindings at once and reports errors neither environment does, while missing
errors CI catches.
