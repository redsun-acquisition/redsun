# dishka sketches

Throwaway. Nothing here is imported by `src/`, nothing is executed, and dishka
is not installed in this environment, so none of it type-checks or runs.

| file | what it shows |
| --- | --- |
| `option1_declarations.py` | Recommended. `declare_*` kept, compiled into a dishka `Provider` at build. Author-facing view, plus the config-driven path. |
| `option2_pure_dishka.py` | Components declared as dishka `Provider`s. `declare_*` deleted. What that costs. |
| `option3_no_dishka.py` | Same ergonomics, hand-rolled on top of `dependency-injector`. No new dependency. |
| `option4_annotated.py` | Option 1's runtime with ophyd-async-style `Annotated` declarations, and what `__class_getitem__` does and does not buy. |
| `container_layer.py` | The container layer under Option 1: keying, factory generation, optional resolution, build phases, `from_config`. |
| `container_v2.py` | **Recommended.** Supersedes `container_layer.py`. `Annotated` declarations, `config` as a ClassVar, no `__init_subclass__`, one declaration concept, attribute name as config key. |
| `mimir_impact.md` | What this does to redsun-mimir, read from its actual source. |
| `late_injection.py` | Postponed injection via a custom dishka scope, for components that need every other component to exist. |
| `genprobe*.py` | Runnable type-checker probes. `uv run pyrefly check genprobe2.py`, or with mypy / ty. |

## `final/` - the whole design in code

| file | |
| --- | --- |
| `_scopes.py` | `AppScope`: RUNTIME, COMPONENT, WIRED. |
| `_declarations.py` | Markers, `Declaration`, and reading annotations off a container class. |
| `_factories.py` | Factory generation, optional resolution, scope inference. |
| `container.py` | `AppContainer`. |
| `mimir_providers.py` | What `redsun_mimir/providers.py` becomes. |
| `mimir_app.py` | What a bundle author writes, end to end. |

All three checkers (mypy, pyrefly 1.2.0, ty 0.0.71) agree on every case in the
probes, so the conclusions do not depend on which one the project uses.

Decisions these assume, from the brainstorm:

- The root-dependency generic is dropped. It cannot do what it was meant to do.
- Presenters and views keep `name` as their one positional; `devices` becomes
  an injectable `DeviceMap` that only components which use it ask for.
- Devices stay outside the graph, built by `AppContainer`, so a device that
  fails to build is still logged and skipped rather than aborting the app.
- `VirtualContainer` keeps the signal bus and the callback registry, loses the
  DI half, and becomes an ordinary injectable.
- Optional dependencies are resolved statically at registration: if nothing
  provides the type, `None` is bound and the parameter never reaches dishka.
- Sub-components (`DevicePresenter[D]` and the toolkit-bound view counterpart)
  are out of scope; the design must not foreclose them.
