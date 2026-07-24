# redsun — agent & contributor conventions

Single source of conventions for agents (Claude, Copilot) and contributors — cross-link, don't duplicate.

## Repository layout

```
src/redsun/
  virtual/       # VirtualContainer: DI + psygnal signal bus + document callbacks
  containers/    # AppContainer, build phases, YAML config, plugin discovery
                 #   qt/ — Qt-specific container + main view
  device/        # device protocols (HasAsyncShutdown), vector helpers
  engine/        # RunEngine wrapper, actions, plan stubs, exceptions
  presenter/     # Presenter ABC, plan_spec, utils
  view/          # View base; qt/ — widget factory, treeview, sequence edit
  storage/       # FSM, BaseStorage/SinkFactory, path provider, FrameRouter
                 #   backends/ — _memory, _acquire_zarr
  common/ utils/ aio.py log.py
docs/            # zensical + mkdocstrings, Diataxis (see below)
tests/sdk/       # per-subsystem unit tests
tests/container/ # container build/plugin-discovery tests + mock_pkg fixtures
pyproject.toml   # all tool config: pytest, ruff, mypy, coverage
```

## Build & validate

```bash
uv sync --group dev                     # dev env (pulls pyqt + zarr groups)
uv run pytest                           # full suite (testpaths=tests)
uv run pytest tests/sdk/storage -x      # scoped, fast
uv run pytest tests/sdk/storage/test_fsm.py::test_name
uv run ruff check --fix . && uv run ruff format .
uv run mypy src/redsun --ignore-missing-imports $(uv run qtpy mypy-args)
uv run zensical build                   # docs
```

- **Windows:** `$(...)` command substitution does not exist in `cmd.exe`. Use
  PowerShell with `@(uv run qtpy mypy-args)`, or just run `/check`, which
  sequences the whole validation suite. Prefer PowerShell over `cmd.exe` for
  Claude Code sessions on this repo.
- **Use the qtpy shim form of mypy** — `$(uv run qtpy mypy-args)` pins the Qt
  binding mypy resolves against. This is exactly what CI runs, so it's the only
  invocation whose result is authoritative. A bare `mypy src/redsun` may agree
  when only one binding is installed, but diverges once both pyqt6 and pyside6
  are present.
- mypy is `strict = true` with `warn_unreachable`; `files = "."` but `tests/`
  and `docs/` are excluded. Only `import-untyped` and `no-untyped-call` are
  globally disabled — do not widen that list to silence a real error.
- pytest is `asyncio_mode = "auto"` — **do not decorate async tests** with
  `@pytest.mark.asyncio`. `QT_QPA_PLATFORM=offscreen` is set via pytest-env.
- Qt tests take `@pytest.mark.qt`; the root `conftest.py` auto-skips them
  headless. Use the session-scoped `qapp` fixture, never build a `QApplication`.

## Architecture invariants

- **`VirtualContainer`** subclasses `dependency_injector.DynamicContainer` and
  is simultaneously the DI container, the psygnal signal bus, and the
  document-callback registry. Config is frozen (`_FrozenConfig`) — read it via
  the `schema_version` / `frontend` / `session` / `metadata` properties.
- **`AppContainer.build()` phase order is load-bearing** and documented in its
  docstring: VirtualContainer → devices → presenters → views → `register_providers`
  → `inject_dependencies`. Providers must all be registered before any injection
  runs; never interleave the last two phases, never move work into `__init__`
  that belongs in a phase.
- Device build failures are logged and skipped; presenter/view build failures
  re-raise. Preserve that asymmetry — a missing device must not abort the app.
- Wiring is protocol-based, not inheritance-based: `IsProvider`, `IsInjectable`,
  `HasShutdown` (sync, presenters) and `HasAsyncShutdown` (async, devices) are
  `@runtime_checkable` Protocols checked with `isinstance`.

### Storage

- Two-level split: **`StorageIO`** is backend mechanics (`open`, `uri`,
  `resource_info`); **`OpenStore`** is the lifecycle-bound handle (`write`,
  `release`, `close`). `BaseStorage` implements the `SinkFactory` protocol on
  top of both. Keep the split — do not give `StorageIO` lifecycle methods.
- **`StorageStateMachine`**: UNSEALED → SEALING → OPEN → CLOSING → UNSEALED.
  All transitions go through the machine; never assign `_state` elsewhere.
  Concurrent first-writers race through `try_seal()`: the winner opens, the
  losers park in `await_open()`. Invalid transitions raise `InvalidStoreState`.
- `try_seal()` is deliberately called *outside* the try/except in
  `_open_and_write` — a CLOSING seal opened nothing and parked nobody, so
  routing it through `open_failed()` would raise a second `InvalidStoreState`
  and mask the real bug. Read the comment before touching that block.
- **Capacity is enforced by the generator, not by exceptions.** `FrameSender` is
  `AsyncGenerator[None, NDArray]`; `_pusher` writes the first frame, then loops
  `capacity - 1` more times (or forever when `StreamSpec.is_unbounded`). The
  generator returning is the signal — do not raise `StopAsyncIteration` by hand.
  `_pusher`'s `finally` pops the sink and releases; that cleanup must stay in
  `finally`.
- `FrameRouter` owns per-key `StreamSpec` and `SignalR[int]` counters;
  `mark_written` is the single place frame counts advance.

## Code conventions

- Python ≥3.11, `from __future__ import annotations` everywhere (ruff `FA102`).
- Ruff lint has `D` (numpy docstring convention) and `TC` (type-check imports)
  enabled: runtime-unneeded imports go under `if TYPE_CHECKING:`. Public
  symbols need docstrings; `D100`/`D104` are ignored.
- Private modules are `_underscored`; the package `__init__.py` re-exports the
  public surface with explicit `__all__`. Add new public symbols to both.
- asyncio only — no threads for I/O. Hardware goes through `ophyd-async`.
- Public API change ⇒ docstring + `CHANGELOG.md` entry.

## Testing conventions

- Mirror the source layout under `tests/sdk/`. Container/plugin-discovery tests
  live in `tests/container/` and use the `mock_pkg/` fixture package — extend
  that package rather than inventing new mock plugins elsewhere.
- Prefer the public interface. For a multi-step lifecycle (register → write →
  close) write one happy-path test driving the whole sequence and asserting the
  observable end state, then small focused tests for unhappy paths.
- Parametrize normal and edge cases together in one `@pytest.mark.parametrize`.
- `src/redsun/view/**` is omitted from coverage; don't chase coverage there.

## Docs conventions

- Diataxis under `docs/`: `tutorials/` (learning), `how-to/` (task),
  `explanation/` (rationale), `reference/api/` (mkdocstrings-generated facts).
- One authoritative source per fact; cross-link instead of restating.
- Material-style admonitions (`!!! warning`), mermaid fences for diagrams.
- Reference pages are generated from docstrings — fix the docstring, not the
  `.md`, when reference content is wrong.

## Response style (agents)

- Terse. No preamble, no restatement of the request, no summary of what you
  just did.
- Show diffs, not whole files. Don't explain code unless asked.
- Don't narrate intent ("I'll now…") — just make the change.
- State assumptions in one line; ask only when genuinely blocked.

## Updating this guide

Say **"Update CLAUDE.md with…"** to persist a convention here. Durable,
shareable rules belong in this file — not in per-session memory.
