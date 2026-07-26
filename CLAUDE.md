# redsun — agent & contributor conventions

Single source of conventions for agents (Claude, Copilot) and contributors — cross-link, don't duplicate.

Things the tree does not show:

- `src/redsun/device/` holds device protocols only — `DeviceMap` comes from
  ophyd-async, not from this package.
- `benchmarks/` are not tests and are never collected by pytest; they ship in
  the sdist only. Run one with
  `uv run python benchmarks/bench_acquire_zarr.py`.
- `pyproject.toml` carries all tool config: pytest, ruff, mypy, coverage.

## Build & validate

```bash
uv sync --group dev                     # dev env (pulls pyqt + zarr groups)
uv run pytest                           # full suite (testpaths=tests)
uv run pytest tests/sdk/storage -x      # scoped, fast
uv run pytest tests/sdk/storage/test_base_storage.py::test_name
uv run ruff check --fix . && uv run ruff format .
uv run mypy --ignore-missing-imports $(uv run qtpy mypy-args)
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
- mypy is `strict = true` with `warn_unreachable`; `files = "."` with only
  `docs/` excluded — **tests are strictly type-checked too**. `mypy_path`
  (`src`, `tests/container`) + `explicit_package_bases` make `mock_pkg`
  resolve; don't run mypy with an explicit path argument or tests fall out
  of scope. Only `import-untyped` and `no-untyped-call` are globally
  disabled — do not widen that list to silence a real error.
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
- `PPresenter`/`PView` data members are **read-only properties** — never make
  them plain attributes (breaks structural subtyping for property-based and
  covariant implementers). The `Presenter`/`View` ABCs must NOT inherit the
  protocols (property descriptors shadow instance attributes at runtime).
  Presenter/view validation is a **dual gate**: constructor positional shape
  (`(name, devices)` / `(name,)` via `expects_positionals`) at
  declaration/discovery, protocol `isinstance` on the **built instance** in
  `_PresenterComponent.build`/`_ViewComponent.build`. Never reintroduce
  class-level attribute checks.
  Rationale: `docs/explanation/decisions/0003-structural-subtyping-for-presenters-and-views.md`.

### Storage

- Two-level split: **`StorageIO`** is backend mechanics (`open`, `uri`,
  `resource_info`); **`OpenStore`** is the lifecycle-bound handle (`write`,
  `release`, `close`). `BaseStorage` implements the `SinkFactory` protocol on
  top of both. Keep the split — do not give `StorageIO` lifecycle methods.
- Producers only ever hold a **`FrameSink`** (`await put` / `put_nowait` /
  `close`). The consumer face of the queue is private to `BaseStorage`'s
  per-key drain task; all per-key teardown flows through the drain's exit
  path, and the last drain out closes the backend.
- `open()` is idempotent and lock-guarded — never open the backend anywhere
  else. `register` is sync and only legal before open.
- **Capacity is enforced by the drain, not by exceptions**: the drain counts
  writes and shuts the queue down at capacity; producers observe
  `QueueShutDown`. Never raise it by hand.
- `FrameRouter.mark_written` is the single place frame counts advance.
- Design rationale: `docs/explanation/decisions/0002-storage-dual-context-redesign.md`.

## Code conventions

- Python ≥3.11, `from __future__ import annotations` everywhere (ruff `FA102`).
- Ruff lint has `D` (numpy docstring convention) and `TC` (type-check imports)
  enabled: runtime-unneeded imports go under `if TYPE_CHECKING:`. Public
  symbols need docstrings; `D100`/`D104` are ignored.
- Private modules are `_underscored`; the package `__init__.py` re-exports the
  public surface with explicit `__all__`. Add new public symbols to both.
- psygnal signal attributes are `sig_snake_case` (the `sig_` prefix is
  optional), never `sigCamelCase`. Same-named signals across components are
  discerned by owner: `find_signals(container, names, owner=...)` (ADR 0004).
- asyncio only — no threads for I/O. Hardware goes through `ophyd-async`.
- Public API change ⇒ docstring + `CHANGELOG.md` entry.

### Docstrings and comments

- Docstrings are concise and minimal: only the behaviour of the thing being
  defined, scoped to that definition. Write for a reader who has nothing but
  the docstring in front of them — no ADR numbers, no references to design
  documents, no history of previous designs. Rationale belongs in `docs/`,
  which is where a reader can follow it; ADRs are cross-linked from this file
  and from the docs, never from a docstring.
- Don't restate the signature in prose, and don't document parameters whose
  meaning the name and type already carry.
- No section-divider or banner comments, and no comment blocks describing the
  code that follows. A comment earns its place only by explaining why a
  specific statement is the way it is.

## Testing conventions

- Mirror the source layout under `tests/sdk/`. Container/plugin-discovery tests
  live in `tests/container/` and use the `mock_pkg/` fixture package — extend
  that package rather than inventing new mock plugins elsewhere.
- Prefer the public interface. For a multi-step lifecycle (register → write →
  close) write one happy-path test driving the whole sequence and asserting the
  observable end state, then small focused tests for unhappy paths.
- Parametrize normal and edge cases together in one `@pytest.mark.parametrize`.
- **All imports live at the top of the module** — in tests too. No
  function-level or method-level imports; runtime-unneeded imports go under
  the module's `if TYPE_CHECKING:` block like everywhere else.
- `src/redsun/view/**` is omitted from coverage; don't chase coverage there.

## Docs conventions

See the `docs-conventions` skill — Diataxis layout, ADR recording, and the
mkdocstrings pitfalls that a green `zensical build` will not catch.

## Response style (agents)

- Terse. No preamble, no restatement of the request, no summary of what you
  just did.
- Show diffs, not whole files. Don't explain code unless asked.
- Don't narrate intent ("I'll now…") — just make the change.
- State assumptions in one line; ask only when genuinely blocked.
- `.claude/agents/*` files stay slim: scope, verify commands, and pointers to
  CLAUDE.md / ADRs. Never restate invariants there — cross-link instead.

## Updating this guide

Say **"Update CLAUDE.md with…"** to persist a convention here. Durable,
shareable rules belong in this file — not in per-session memory.
