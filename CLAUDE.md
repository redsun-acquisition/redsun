# redsun agent & contributor conventions

Single source of conventions for agents (Claude, Copilot) and contributors:
cross-link, don't duplicate.

## Repository layout

```text
redsun/
|-- src/redsun/
|   |-- __init__.py            what a component author imports: Session, AsDevice, ...
|   |-- aio.py                 shared background event loop, run_coro
|   |-- log.py                 redsun logger, buffer, session log files
|   |-- plugins.yaml           manifest of the built-in views
|   |-- session/               Session, declarations, build steps, plugin loading
|   |-- qt/                    QtSession, placements, actions, colour scheme
|   |-- ports/                 slot, connections, wiring errors
|   |-- injection/             provides, DevicesOf, shared values
|   |-- registry/              SessionConfig, PlanEntry, CallbackType, DeviceMapping
|   |-- engine/                RunEngine wrapper, actions, plan stubs
|   |-- presenter/             plan spec: plan signatures read into widget descriptions
|   |-- services/              Service: a process or server devices talk to
|   |-- path_provider.py       SessionPathProvider, session_directory
|   |-- _config.py             session file loading, merging and validation
|   |-- _catalog.py            require_tiled, start_catalog
|   |-- writers/               Writer for derived products, one stream per format
|   |-- view/                  Placement
|   |   `-- qt/                Qt widgets and the built-in LogView
|   `-- utils/                 descriptor helpers, session_folder (_paths.py)
|-- tests/
|   |-- conftest.py            qt marker, qapp, log directory, psygnal queue, build
|   |-- test_*.py              session tests, one module per subject
|   |-- mock_bundle/           fake plugin package the session tests discover
|   |-- configs/               session YAML files the tests load
|   |-- launchable/mock_pkg/   service stand-ins a test launches as processes
|   |-- sdk/                   unit tests of the shared modules
|   |-- compose/               an IOC in a container, for the tests marked compose
|   `-- typing/                assert_type modules, checked by mypy, never run
|-- docs/                      Diataxis site built by zensical
|   |-- tutorials/             installation, first session
|   |-- how-to/                one task per page, contributing and migration included
|   |-- explanation/           architecture pages and decisions/ (ADRs)
|   `-- reference/             api/ pages, glossary, changelog (generated)
|-- benchmarks/                performance scripts, not tests, sdist only
|-- scripts/                   check_xrefs.py (docs), mypy_qt.py (tox mypy legs),
|                              release_notes.py (changelog sections),
|                              screenshots.py (tutorial window pictures, docs build)
|-- .github/workflows/         CI, changelog label check, prepare-release
|-- .claude/                   agents, commands, docs-conventions skill
|-- pyproject.toml             dependencies and all tool config: pytest, ruff, mypy, coverage, tox
|-- zensical.toml              docs site and navigation
`-- uv.lock
```

- There is no device package: devices, `DeviceMap` included, come from
  ophyd-async.
- `redsun.utils` imports nothing from `redsun` at runtime, only under
  `TYPE_CHECKING`: `log.py` imports `redsun.utils._paths`, so a runtime import
  there would be circular.
- `benchmarks/` are never collected by pytest. Run one with
  `uv run python benchmarks/bench_acquire_zarr.py`.

## Build & validate

`tox` is the entry point, configured under `[tool.tox]` in `pyproject.toml`.
Every environment installs from `uv.lock` through `tox-uv-bare`, so a local run
uses the versions CI resolves rather than whatever the project `.venv`
accumulated. The plugin is `tox-uv-bare` rather than `tox-uv` so that the `uv`
it drives is the one on `PATH`: `tox-uv` depends on the `uv` package, which puts
a second `uv.exe` in the project `.venv` and shadows the installed one:

```bash
uv run prek install              # once: run the prek.toml hooks on every commit
uv run tox                       # lint, both mypy legs, tests, docs
uv run tox -e tests              # one environment
uv run tox -e tests -- tests/sdk -x              # posargs reach pytest
uv run tox -e mypy-pyqt,mypy-pyside
```

| environment | what it runs |
| --- | --- |
| `lint` | `prek run --all-files`: the commit hooks, ruff included |
| `mypy-pyqt` / `mypy-pyside` | mypy against that binding |
| `tests` | `pytest -q` |
| `docs` | `zensical build` then `scripts/check_xrefs.py` |

**Run what the change can break, not the whole matrix.** A change confined to
`docs/` (pages, ADRs, changelogs, `zensical.toml`) can only break the docs
build, so validate it with `uv run tox -e docs` alone. A change to docstrings
in `src/` also runs `lint`, since ruff's `D` rules check docstrings and the
reference pages render them: `uv run tox -e lint,docs`. Anything touching code
or tests runs the full `uv run tox`.

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
  (`src`, `tests/launchable`) + `explicit_package_bases` make `mock_pkg`
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

- **`Session.build()` step order cannot change**, and `BUILD_STEPS` records
  it: services -> devices -> connect -> registry -> presenters -> views ->
  setup -> seal -> wiring -> presentation -> report, after
  `read_configuration` and `start_runtime`. Never move work into `__init__`
  that belongs in a step.
- **Services start in the first build step.** Each stop is registered as a
  release, so `shutdown()` stops them after every component, and a build that
  raises runs its releases before the exception leaves it.
- **A component that fails to build is logged and skipped.** The build records
  the exception under the component's name in `_failed` and carries on, so a
  session runs with what it has, and the `devices`/`presenters`/`views`
  mappings can be shorter than what was declared.
  Rationale: `docs/explanation/decisions/0011-tolerating-a-component-that-fails-to-build.md`.
- Components conform by shape, never by inheritance: `NamedComponent`,
  `AttachableComponent`, `HasSetup` and `HasShutdown` are protocols checked on
  the built instance.
- A presenter or view is checked twice: at declaration (layer, a `name` a
  keyword can fill, placement, `Frontend.check_view`), then on the **built
  instance** against its layer's protocol. A failed check skips the component.
  Rationale: `docs/explanation/decisions/0016-a-component-refused-at-declaration-is-skipped.md`.

### Acquisition storage

- `redsun` writes no acquisition bytes. The service and its device choose the
  format, the dimensions and when a file is complete, and emit
  `StreamResource` / `StreamDatum` documents naming the result.
- The container builds one `SessionPathProvider` per session and passes it to
  every device whose constructor takes a `path_provider` keyword. A
  declaration giving that keyword is refused, as with `service` and
  `autoconnect`.
- `redsun.writers` holds the `Writer` for derived products only: a
  component computing one writes it against the store named in the
  `StreamResource` document.
- Rationale: `docs/explanation/decisions/0013-acquisition-storage-belongs-to-the-device.md`.

## Code conventions

- Python >=3.11, `from __future__ import annotations` everywhere (ruff
  `FA102`).
- **Module-level names come first, after the imports:** constants, type
  aliases, `TypeVar`s and `ParamSpec`s, before any function or class. A
  reader finds every name the module is built on in one place. The one
  exception is a name built from something the module defines, such as
  `ClassPath = Annotated[str, AfterValidator(class_path)]`: it goes directly
  after that definition.
- Ruff lint has `D` (numpy docstring convention) and `TC` (type-check imports)
  enabled: runtime-unneeded imports go under `if TYPE_CHECKING:`. Public
  symbols need docstrings; `D100`/`D104` are ignored.
- Private modules are `_underscored`; the package `__init__.py` re-exports the
  public surface with an explicit `__all__`. Add new public symbols to both.
- **Import a private module relatively, a public one absolutely.** A module
  whose dotted path has an `_underscored` part, `_config` or `utils._paths`,
  is imported as `from ._config import ...` or `from ..utils._paths import
  ...`; a public one as `from redsun.path_provider import ...`, even from
  inside its own package. Tests import everything absolutely, since they are
  not part of the package.
- **The underscore marks what `__all__` cannot.** A module named `_foo.py` is
  private in its entirety, so its **module-level members carry no underscore**:
  the module name already said it. **Class members always keep the
  underscore**, in a private module too, because `__all__` is module-scoped and
  can never say that a method is private, and both the docs filter
  (`filters = ["!^_", "!^__"]` in `zensical.toml`) and a reader's autocomplete
  key on the name. So `_hooks.py` holds `parse_hook_specs`, while
  `Session._declarations` stays underscored.
  **A class no `__all__` re-exports is private as a whole**, so its members
  drop the underscore too: the session-file and manifest models in `_config`
  and `_manifest` name their validators `group_hooks`, not `_group_hooks`. The
  class-member rule above is for classes a user can reach.
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
- **Don't annotate what the assignment already says.** `HOOK_GROUPS =
  TypeAdapter(list[HookGroup])`, not `HOOK_GROUPS: TypeAdapter[list[HookGroup]]
  = ...`. Annotate where mypy cannot infer the type (an empty container, an
  `Any` from `getattr`, a narrower declared type).
- **Don't alias an attribute to a local for a single use.** Write
  `self.main_window.show()`. A local earns its place when the value is read
  several times and reaching it costs something, when a type checker needs the
  narrowing, or when repeating the expression would hide the line.
- **No comments in the import block.** Not above an import, not above a group,
  and not to explain a `# noqa`. The suppression code already names the rule.
  If a runtime import is surprising, say why at the annotation that needs it.
- asyncio only, no threads for I/O. Hardware goes through `ophyd-async`.
- Public API change -> docstring, and a changelog label on the pull request.
  The changelog is written from the labels at release time
  (`docs/how-to/make-a-release.md`); never edit `docs/reference/changelog.md` by
  hand. A change that breaks existing code also gets the `breaking` label and a
  line on the current `docs/how-to/migrate-from-*.md` page.

### Docstrings and comments

- Docstrings are concise and minimal: only the behaviour of the thing being
  defined, scoped to that definition. Write for a reader who has nothing but
  the docstring: no ADR numbers, no design documents, no history of previous
  designs. Rationale belongs in `docs/`, which is where a reader can follow it.
- Don't restate the signature in prose, and don't document parameters whose
  meaning the name and type already carry. A `Parameters`, `Returns` or
  `Raises` section earns its place when it says something the signature cannot:
  units, accepted values, what `None` means, which exception and when.
- **Attributes are documented where they are declared**, by a docstring on the
  line after each one, never by a `Parameters` or `Attributes` section in the
  class docstring. This holds for everything declared as fields: dataclasses,
  `pydantic` models, `TypedDict`s, `NamedTuple`s.

  ```python
  class ServiceEntry(BaseModel):
      """How a manifest launches a service."""

      module: str
      """Module run as ``python -m <module>``."""
  ```
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
- `src/redsun/view/**` is omitted from coverage; don't chase coverage there.
- **A property only a type checker can observe is tested in `tests/typing/`**,
  with `typing.assert_type`, not with runtime asserts. Those modules are never
  imported or executed: pytest skips them (no `test_` prefix) and mypy checks
  them via `files = "."`. `assert_type` demands an exact match, so an attribute
  regressing to `Any` fails there while every runtime test still passes.

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
- **Library and package names are code spans.** In docs pages write
  `` `redsun` ``, `` `ophyd-async` ``, `` `bluesky` ``, `` `psygnal` ``,
  `` `caproto` ``, `` `pyqt6` ``, at every mention, `redsun` included.
  Docstrings do the same with double backticks (``` ``ophyd-async`` ```), the
  form they use for literals. Headings, link text and a name inside a code
  block stay as they are.

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
