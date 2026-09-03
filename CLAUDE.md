# redsun agent & contributor conventions

Single source of conventions for agents (Claude, Copilot) and contributors: cross-link, don't duplicate.

Things the tree does not show:

- `src/redsun/device/` holds device protocols only; `DeviceMap` comes from
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
uv run python scripts/check_xrefs.py    # docs xref guard (after a build)
```

- **Windows:** `$(...)` command substitution does not exist in `cmd.exe`. Use
  PowerShell with `@(uv run qtpy mypy-args)`, or just run `/check`, which
  sequences the whole validation suite. Prefer PowerShell over `cmd.exe` for
  Claude Code sessions on this repo.
- **Use the qtpy shim form of mypy** - `$(uv run qtpy mypy-args)` pins the Qt
  binding mypy resolves against. This is exactly what CI runs, so it's the only
  invocation whose result is authoritative. A bare `mypy src/redsun` may agree
  when only one binding is installed, but diverges once both pyqt6 and pyside6
  are present.
- mypy is `strict = true` with `warn_unreachable`; `files = "."` with only
  `docs/` excluded, so **tests are strictly type-checked too**. `mypy_path`
  (`src`, `tests/container`) + `explicit_package_bases` make `mock_pkg`
  resolve; don't run mypy with an explicit path argument or tests fall out
  of scope. Only `import-untyped` and `no-untyped-call` are globally
  disabled; do not widen that list to silence a real error.
- pytest is `asyncio_mode = "auto"`, so **do not decorate async tests** with
  `@pytest.mark.asyncio`. `QT_QPA_PLATFORM=offscreen` is set via pytest-env.
- Qt tests take `@pytest.mark.qt`; the root `conftest.py` auto-skips them
  headless. Use the session-scoped `qapp` fixture, never build a `QApplication`.

## Architecture invariants

- **`VirtualContainer`** subclasses `dependency_injector.DynamicContainer` and
  is simultaneously the DI container, the psygnal signal bus, and the
  document-callback registry. Config is frozen (`_FrozenConfig`); read it via
  the `schema_version` / `frontend` / `session` / `metadata` properties.
- **`AppContainer.build()` phase order is load-bearing** and documented in its
  docstring: VirtualContainer -> devices -> presenters -> views ->
  `register_providers` -> `wire` -> `inject_dependencies`. Providers must all
  be registered before any injection runs; never interleave the last two phases,
  never move work into `__init__` that belongs in a phase.
- Device build failures are logged and skipped; presenter/view build failures
  re-raise. Preserve that asymmetry: a missing device must not abort the app.
- **An application is built, run and shut down once.** `build()` refuses a
  second call while the container is built, and a shut-down container is
  finished rather than reset: nothing supports building it again in the same
  script. Do not add state a rebuild would have to clear, and do not write
  docstrings promising one.
- A phase that raises once the components are built (providers, wiring,
  injection) runs the shutdown phases through `AppContainer._teardown` before
  re-raising, since `shutdown()` returns without acting on a container that
  never finished building. The component build phases stay outside that, so
  the asymmetry above is what decides the fate of a component that fails.
- Wiring is protocol-based, not inheritance-based: `IsProvider`, `IsInjectable`,
  `HasShutdown` (sync, presenters) and `HasAsyncShutdown` (async, devices) are
  `@runtime_checkable` Protocols checked with `isinstance`.
- `PPresenter`/`PView` data members are **read-only properties**; never make
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
  top of both. Keep the split: do not give `StorageIO` lifecycle methods.
- Producers only ever hold a **`FrameSink`** (`await put` / `put_nowait` /
  `close`). The consumer face of the queue is private to `BaseStorage`'s
  per-key drain task; all per-key teardown flows through the drain's exit
  path, and the last drain out closes the backend.
- `open()` is idempotent and lock-guarded; never open the backend anywhere
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
- **The underscore marks what `__all__` cannot.** A module named `_foo.py` is
  private in its entirety, so its **module-level members carry no underscore** -
  the module name already said it, and repeating it at every call site is noise.
  What is public is what the package `__init__.py` lists in `__all__`.
  **Class members always keep the underscore**, in a private module too:
  `__all__` is module-scoped and can never say that a method is private, and the
  docs filter (`filters = ["!^_", "!^__"]` in `zensical.toml`) and a reader's
  autocomplete both key on the name. So `_hooks.py` holds `parse_hook_specs`,
  but `AppContainer._build_devices` stays underscored.
  Two consequences: ruff `D103` treats a non-underscore function as public, so
  helpers in a private module need docstrings; and a reference page targeting a
  *module* rather than an object needs an explicit `members:` list, because
  mkdocstrings selects `__all__` **union** non-underscore members, never
  `__all__` alone.
- Public methods are named in the imperative: `wire`, `build`, `connect`,
  `release`, not `wiring`, `building` or `connection`. A method does something;
  the name says what it does, not what it is. Nouns are for the things a method
  returns or holds (`connections`, `ports`, `signals`), which are properties.
  Deviate only where an established external convention requires it.
- **`@property` is for public API only.** It exists to give a class a read-only
  attribute that callers can rely on; a leading underscore says there are no
  such callers, so the two do not combine. Private state is a plain attribute,
  computed once where it is first known - usually `__init__` - and added to
  `__slots__`. Private *behaviour* is an ordinary underscored method. A private
  property recomputes on every access with none of the guarantee it buys.
- psygnal signal attributes are `sig_snake_case` (the `sig_` prefix is
  optional), never `sigCamelCase`. Same-named signals across components are
  discerned by owner: `find_signals(container, names, owner=...)` (ADR 0004).
- **A `__slots__` class that owns a psygnal `Signal` needs `__weakref__` among
  its slots.** psygnal refers to a signal's owner weakly, and silently falls
  back to a strong reference when it cannot; a slotted class cannot be referred
  to weakly without that slot, and on the fallback the owner is never collected
  - taking everything it holds with it. A class with a `__dict__` never reaches
  that path, so this only bites where `__slots__` is declared.
- asyncio only, no threads for I/O. Hardware goes through `ophyd-async`.
- Public API change -> docstring + `docs/reference/changelog.md` entry. The root
  `CHANGELOG.md` is only a redirect to it; never add entries there.

### Docstrings and comments

- Docstrings are concise and minimal: only the behaviour of the thing being
  defined, scoped to that definition. Write for a reader who has nothing but
  the docstring in front of them: no ADR numbers, no references to design
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
  live in `tests/container/` and use the `mock_pkg/` fixture package; extend
  that package rather than inventing new mock plugins elsewhere.
- Prefer the public interface. For a multi-step lifecycle (register -> write ->
  close) write one happy-path test driving the whole sequence and asserting the
  observable end state, then small focused tests for unhappy paths.
- Parametrize normal and edge cases together in one `@pytest.mark.parametrize`.
- **All imports live at the top of the module**, in tests too. No
  function-level or method-level imports; runtime-unneeded imports go under
  the module's `if TYPE_CHECKING:` block like everywhere else.
- `src/redsun/view/**` is omitted from coverage; don't chase coverage there.
- **A property that only a type checker can observe is tested in
  `tests/typing/`**, with `typing.assert_type`, not with runtime asserts. Those
  modules are never imported or executed: pytest skips them (no `test_` prefix)
  and mypy checks them via `files = "."`. `assert_type` demands an exact match,
  so an attribute regressing to `Any` fails there while every runtime test still
  passes. `tests/typing/component_attributes.py` pins the `declare_*` returns.

## Docs conventions

See the `docs-conventions` skill: Diataxis layout, ADR recording, and the
mkdocstrings pitfalls that a green `zensical build` will not catch.

- **Examples are agnostic.** Every snippet, class name and configuration
  fragment in the docs is written for a reader who has only this repository.
  Name nothing from another project - not a downstream bundle, not a plugin,
  not a class that lives outside `redsun` - unless the passage is explicitly
  about that project. Reach for the placeholder names the surrounding page
  already uses (`MyApp`, `MyMotor`, `MyController`, `MyView`, `mylab.thing:X`)
  rather than inventing one from whatever motivated the change.
- The motivating case is usually a real downstream session, and writing its
  names into a snippet is the easiest mistake to make: it reads correctly to
  whoever wrote it and names nothing the reader can look up. An ADR recording a
  decision that genuinely spanned two repositories is the exception, and says
  so.

## Response style (agents)

- Terse. No preamble, no restatement of the request, no summary of what you
  just did.
- Show diffs, not whole files. Don't explain code unless asked.
- Don't narrate intent ("I'll now..."); just make the change.
- State assumptions in one line; ask only when genuinely blocked.
- `.claude/agents/*` files stay slim: scope, verify commands, and pointers to
  CLAUDE.md / ADRs. Never restate invariants there; cross-link instead.

## Updating this guide

Say **"Update CLAUDE.md with..."** to persist a convention here. Durable,
shareable rules belong in this file, not in per-session memory.
