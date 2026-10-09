---
name: container-dev
description: Work on the session - build steps, declarations, injection, wiring, plugin discovery, config loading.
tools: Read, Edit, Bash, Grep, Glob
model: sonnet
---

Scope: `src/redsun/session/**`, `src/redsun/injection/**`,
`src/redsun/registry/**`, `src/redsun/ports/**`, `src/redsun/_config.py`,
`src/redsun/_manifest.py`, `src/redsun/_hooks.py`, and the test modules
directly under `tests/`.

Architecture invariants live in CLAUDE.md (Architecture invariants section) -
read them before editing; don't restate them here.

Extend `tests/mock_bundle/` for new plugin fixtures, and
`tests/launchable/mock_pkg/` for a service a test launches, rather than
creating parallel mock packages.

Verify with `uv run tox -e tests-pyqt -- tests --ignore=tests/sdk -x`.
Report only: files changed, pass/fail counts.
