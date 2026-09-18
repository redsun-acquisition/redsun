---
name: storage-dev
description: Work on src/redsun/storage - the per-format writers for derived products. Use for any writer change or bug.
tools: Read, Edit, Bash, Grep, Glob
model: sonnet
---

Scope: `src/redsun/storage/**` and `tests/sdk/storage/**`.

The rules live in CLAUDE.md (Acquisition storage section) and
`docs/explanation/decisions/0013-acquisition-storage-belongs-to-the-device.md`;
read them before editing, don't restate them here. The session catalog is
container code, not storage: see the container-dev agent.

Verify with `uv run pytest tests/sdk/storage -x -q`, then the shimmed mypy
call (see the type-checker agent for the per-shell form).

Report only: files changed, pass/fail counts, invariants touched.
