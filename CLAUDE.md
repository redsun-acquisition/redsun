# redsun agent & contributor conventions

Single source of conventions for agents (Claude, Copilot) and contributors:
cross-link, don't duplicate.

Things the tree does not show:

- `src/redsun/device/` holds device protocols only; `DeviceMap` comes from
  ophyd-async, not from this package.
- `benchmarks/` are not tests and are never collected by pytest; they ship in
  the sdist only. Run one with `uv run python benchmarks/bench_acquire_zarr.py`.
- `pyproject.toml` carries all tool config: pytest, ruff, mypy, coverage, tox.

## Build & validate

`tox` is the entry point, configured under `[tool.tox]` in `pyproject.toml`.
Every environment installs from `uv.lock` through `tox-uv`, so a local run uses
the versions CI resolves rather than whatever the project `.venv` accumulated:

```bash
uv run tox                       # lint, both mypy legs, tests, docs
uv run tox -e tests              # one environment
uv run tox -e tests -- tests/sdk/storage -x     # posargs reach pytest
uv run tox -e mypy-pyqt,mypy-pyside
```

| environment | what it runs |
| --- | --- |
| `lint` | `ruff check --fix` then `ruff format` |
| `mypy-pyqt` / `mypy-pyside` | mypy against that binding |
| `tests` | `pytest -q` |
| `docs` | `zensical build` then `scripts/check_xrefs.py` |

The project `.venv` still works for a quick loop (`uv run pytest -q`), but it
is not authoritative: it holds every group any `uv sync` has installed, both Qt
bindings included. One such run reported five `QAction` errors tox does not,
and missed the one CI failed on. Trust tox.

### The Qt binding matrix

CI type-checks against pyqt6 **and** pyside6, and runs the tests against pyqt6
alone. `mypy-pyqt` and `mypy-pyside` each sync only their own binding's group
and set `QT_API`, which is what decides the branches qtpy exposes.

`scripts/mypy_qt.py` is what the two environments call. `qtpy mypy-args` prints
the `--always-true` / `--always-false` flags for the selected binding, and
composing that with mypy needs command substitution, which `cmd.exe` lacks and
no tox `commands` line can express; the script does both in one process.

The bindings disagree on some signatures, so one annotation may not satisfy
both. `QWidget.closeEvent` takes `QCloseEvent | None` under pyqt6 and
`QCloseEvent` under pyside6: widen the override to accept `None` and guard the
`super()` call.

- mypy is `strict = true` with `warn_unreachable`; `files = "."` with only
  `docs/` excluded, so **tests are strictly type-checked too**. `mypy_path`
  (`src`, `tests/container`) + `explicit_package_bases` make `mock_pkg`
  resolve; don't pass mypy an explicit path or tests fall out of scope. Only
  `import-untyped` and `no-untyped-call` are globally disabled; do not widen
  that list to silence a real error.
- pytest is `asyncio_mode = "auto"`, so **do not decorate async tests** with
  `@pytest.mark.asyncio`. `QT_QPA_PLATFORM=offscreen` comes from pytest-env.
- Qt tests take `@pytest.mark.qt`; the root `conftest.py` auto-skips them
  headless. Use the session-scoped `qapp` fixture, never build a
  `QApplication`. The fixture holds one for the whole run: a session that
  creates and destroys its own aborts the interpreter on the next test.

## Architecture invariants

- **`VirtualContainer`** subclasses `dependency_injector.DynamicContainer` and
  is at once the DI container, the psygnal signal bus, and the
  document-callback registry. Config is frozen (`_FrozenConfig`); read it
  through the `schema_version` / `frontend` / `session` / `metadata`
  properties.
- **`AppContainer.build()` phase order cannot change**, and its docstring
  records it: VirtualContainer -> devices -> presenters -> views ->
  `register_providers` -> `wire` -> `inject_dependencies`. Every provider is
  registered before any injection runs; never interleave the last two phases,
  and never move work into `__init__` that belongs in a phase.
- **A component that fails to build is logged and skipped, in every layer.**
  The build records the exception under the component's name in `_failed` and
  carries on, so a session runs with what it has. Phases and the
  `devices`/`presenters`/`views` properties read `_built_of`, never the
  declarations, so a mapping can be shorter than what was declared.
  Rationale: `docs/explanation/decisions/0011-tolerating-a-component-that-fails-to-build.md`.
- Wiring is protocol-based, not inheritance-based: `IsProvider`, `IsInjectable`,
  `HasShutdown` (sync, presenters) and `HasAsyncShutdown` (async, devices) are
  `@runtime_checkable` Protocols checked with `isinstance`.
- `PPresenter`/`PView` data members are **read-only properties**, never plain
  attributes, which would break structural subtyping for property-based and
  covariant implementers. The `Presenter`/`View` ABCs must NOT inherit the
  protocols, property descriptors shadowing instance attributes at runtime.
  A presenter or view is checked twice: constructor shape (`(name, devices)` /
  `(name,)` via `expects_positionals`) at declaration, then protocol
  `isinstance` on the **built instance** in `_PresenterComponent.build`/
  `_ViewComponent.build`. Never reintroduce class-level attribute checks.
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
- Rationale: `docs/explanation/decisions/0002-storage-dual-context-redesign.md`.

## Code conventions

- Python >=3.11, `from __future__ import annotations` everywhere (ruff
  `FA102`).
- Ruff lint has `D` (numpy docstring convention) and `TC` (type-check imports)
  enabled: runtime-unneeded imports go under `if TYPE_CHECKING:`. Public
  symbols need docstrings; `D100`/`D104` are ignored.
- Private modules are `_underscored`; the package `__init__.py` re-exports the
  public surface with an explicit `__all__`. Add new public symbols to both.
- **The underscore marks what `__all__` cannot.** A module named `_foo.py` is
  private in its entirety, so its **module-level members carry no underscore**:
  the module name already said it. **Class members always keep the
  underscore**, in a private module too, because `__all__` is module-scoped and
  can never say that a method is private, and both the docs filter
  (`filters = ["!^_", "!^__"]` in `zensical.toml`) and a reader's autocomplete
  key on the name. So `_hooks.py` holds `parse_hook_specs`, while
  `AppContainer._build_devices` stays underscored.
  Two consequences: ruff `D103` treats a non-underscore function as public, so
  helpers in a private module need docstrings; and a reference page targeting a
  *module* needs an explicit `members:` list, mkdocstrings selecting `__all__`
  **union** non-underscore members.
- Public methods are named in the imperative: `wire`, `build`, `connect`,
  `release`, not `wiring`, `building` or `connection`. Nouns are for what a
  method returns or holds (`connections`, `ports`, `signals`), which are
  properties. Deviate only where an external convention requires it.
- **`@property` is for public API only.** It gives callers a read-only
  attribute they can rely on, and a leading underscore says there are no such
  callers. Private state is a plain attribute, computed once where it is first
  known (usually `__init__`) and added to `__slots__`; private behaviour is an
  ordinary underscored method.
- psygnal signal attributes are `sig_snake_case` (the `sig_` prefix is
  optional), never `sigCamelCase`. Same-named signals across components are
  told apart by owner: `find_signals(container, names, owner=...)` (ADR 0004).
- **A `__slots__` class owning a psygnal `Signal` needs `__weakref__` among its
  slots.** psygnal refers to an owner weakly and falls back silently to a
  strong reference, on which the owner is never collected and takes everything
  it holds with it. Only `__slots__` classes reach that path.
- **Don't alias an attribute to a local for a single use.** Write
  `self.main_window.show()`. A local earns its place when the value is read
  several times and reaching it costs something, when a type checker needs the
  narrowing, or when repeating the expression would hide the line.
- **No comments in the import block.** Not above an import, not above a group,
  and not to explain a `# noqa`. The suppression code already names the rule.
  If a runtime import is surprising, say why at the annotation that needs it.
- asyncio only, no threads for I/O. Hardware goes through `ophyd-async`.
- Public API change -> docstring + `docs/reference/changelog.md` entry. The root
  `CHANGELOG.md` is only a redirect to it; never add entries there.

### Docstrings and comments

- Docstrings are concise and minimal: only the behaviour of the thing being
  defined, scoped to that definition. Write for a reader who has nothing but
  the docstring: no ADR numbers, no design documents, no history of previous
  designs. Rationale belongs in `docs/`, which is where a reader can follow it.
- Don't restate the signature in prose, and don't document parameters whose
  meaning the name and type already carry. A `Parameters`, `Returns` or
  `Raises` section earns its place when it says something the signature cannot:
  units, accepted values, what `None` means, which exception and when.
- No section-divider or banner comments, and no comment blocks describing the
  code that follows. A comment earns its place only by explaining why a
  specific statement is the way it is.

## Testing conventions

- Mirror the source layout under `tests/sdk/`. Container/plugin-discovery tests
  live in `tests/container/` and use the `mock_pkg/` fixture package; extend
  that package rather than inventing new mock plugins elsewhere.
- **Test objects go at the top of the module, after the imports**: mock
  components, the container classes declaring them, fixtures, helpers, in that
  order, before the first test. A test body is then the case it exercises and
  nothing else. A class used by exactly one test may stay inside it.
- **All imports live at the top of the module**, in tests too. No
  function-level or method-level imports; runtime-unneeded imports go under the
  module's `if TYPE_CHECKING:` block.
- Prefer the public interface. For a multi-step lifecycle (register -> write ->
  close) write one happy-path test driving the whole sequence and asserting the
  observable end state, then small focused tests for unhappy paths.
- Parametrize normal and edge cases together in one `@pytest.mark.parametrize`.
- **Falsify a test before trusting it.** Remove the thing it pins, watch it
  fail, put it back. A test that still passes with its subject broken pins
  nothing.
- `src/redsun/view/**` is omitted from coverage; don't chase coverage there.
- **A property only a type checker can observe is tested in `tests/typing/`**,
  with `typing.assert_type`, not with runtime asserts. Those modules are never
  imported or executed: pytest skips them (no `test_` prefix) and mypy checks
  them via `files = "."`. `assert_type` demands an exact match, so an attribute
  regressing to `Any` fails there while every runtime test still passes.
  `tests/typing/component_attributes.py` pins the `declare_*` returns.

## Docs conventions

See the `docs-conventions` skill: Diataxis layout, ADR recording, and the
mkdocstrings mistakes a green `zensical build` will not catch.

- **Examples are agnostic.** Every snippet, class name and configuration
  fragment is written for a reader who has only this repository. Name nothing
  from another project, not a downstream bundle, not a plugin, not a class
  living outside `redsun`, unless the passage is explicitly about that project.
  Use the placeholder names the surrounding page already uses (`MyApp`,
  `MyMotor`, `MyController`, `MyView`, `mylab.thing:X`).
  The motivating case is usually a real downstream session, and writing its
  names in is the easiest mistake to make: it reads correctly to whoever wrote
  it and names nothing the reader can look up. An ADR recording a decision that
  spanned two repositories is the exception, and says so.

## Response style (agents)

- Terse. No preamble, no restatement of the request, no summary of what you
  just did.
- Show diffs, not whole files. Don't explain code unless asked.
- Don't narrate intent ("I'll now..."); just make the change.
- State assumptions in one line; ask only when genuinely blocked.
- No em dashes and no en dashes, anywhere: chat, commits, docs, docstrings,
  comments, PR and issue text. Use a plain hyphen or restructure. Arrows are
  `->` and `<-`, never `→` or `⇒`.
- `.claude/agents/*` files stay slim: scope, verify commands, and pointers to
  CLAUDE.md / ADRs. Never restate invariants there; cross-link instead.

## Updating this guide

Say **"Update CLAUDE.md with..."** to persist a convention here. Durable,
shareable rules belong in this file, not in per-session memory.
