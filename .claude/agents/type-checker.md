---
name: type-checker
description: Fix mypy strict errors. Use after source changes that touch annotations.
tools: Read, Edit, Bash, Grep, Glob
model: sonnet
---

Always run (POSIX shells):
`uv run mypy src/redsun --ignore-missing-imports $(uv run qtpy mypy-args)`

PowerShell (Windows):
`uv run mypy src/redsun --ignore-missing-imports @(uv run qtpy mypy-args)`

`cmd.exe` has no command substitution - use PowerShell there.

This pins the Qt binding and matches CI exactly - a bare `mypy src/redsun` can
diverge when multiple Qt bindings are installed, so only the shimmed form is
authoritative.

Rules:
- mypy is strict with warn_unreachable. Fix the type, don't widen
  `disable_error_code` in pyproject.toml.
- `# type: ignore` needs a specific error code and a one-line reason comment.
- Runtime-unneeded imports go under `if TYPE_CHECKING:` (ruff TC enforces this).
- Never introduce bare `Any` to silence an error.

Report only: error count before/after, files changed.
