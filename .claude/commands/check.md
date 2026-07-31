---
allowed-tools: Bash(uv:*)
description: Run the full local validation suite
---

Run in order, stopping at the first failure:

1. `uv run ruff check --fix . && uv run ruff format .`
2. mypy with the qtpy shim — pick the form matching the current shell:
   - POSIX: `uv run mypy src/redsun --ignore-missing-imports $(uv run qtpy mypy-args)`
   - PowerShell: `uv run mypy src/redsun --ignore-missing-imports @(uv run qtpy mypy-args)`
   - `cmd.exe` has no command substitution. If that's the shell, run
     `uv run qtpy mypy-args` first and paste its output into the mypy call.
3. `uv run pytest -q`
4. `uv run zensical build && uv run python scripts/check_xrefs.py`

Report a one-line result per step. On failure, show the failing output and fix
it, then re-run from that step
