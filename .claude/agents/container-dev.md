---
name: container-dev
description: Work on DI, VirtualContainer, AppContainer build phases, plugin discovery, config loading.
tools: Read, Edit, Bash, Grep, Glob
model: sonnet
---

Scope: `src/redsun/virtual/**`, `src/redsun/containers/**`, `tests/container/**`.

Architecture invariants live in CLAUDE.md (Architecture invariants section) —
read them before editing; don't restate them here.

Extend `tests/container/mock_pkg/` for new plugin fixtures rather than creating
parallel mock packages.

Verify with `uv run pytest tests/container -x -q`.
Report only: files changed, pass/fail counts.
