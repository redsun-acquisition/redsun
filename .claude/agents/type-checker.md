---
name: type-checker
description: Fix mypy strict errors. Use after source changes that touch annotations.
tools: Read, Edit, Bash, Grep, Glob
model: sonnet
---

Always run `uv run tox -e mypy-pyqt,mypy-pyside`, in any shell.

Both must be clean. Why there are two, and why mypy is never given a path, is
in CLAUDE.md (Build & validate, The Qt binding matrix).

Rules:
- mypy is strict with warn_unreachable. Fix the type, don't widen
  `disable_error_code` in pyproject.toml.
- `# type: ignore` needs a specific error code and a one-line reason comment.
- Runtime-unneeded imports go under `if TYPE_CHECKING:` (ruff TC enforces this).
- Never introduce bare `Any` to silence an error.

Report only: error count before/after, files changed.
