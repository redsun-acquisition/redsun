# What dishka has that the sketch was not using

dishka 1.7.x, read from source in `.venv/Lib/site-packages/dishka`, then run.
Spikes: `spike.py` / `spike2.py` in the session scratchpad, `genprobe4.py` here.

## First: the sketched design runs

The whole mechanism was exercised against real dishka, and all of it passes.

```
PASS  synthesized factory resolves
PASS  config kwargs bound, not injected
PASS  NewType keys stay distinct
PASS  @provides bound to instance
PASS  absent optional bound as None
PASS  class alias for unique decl
PASS  WIRED sees COMPONENT side effects
PASS  COMPONENT cannot reach WIRED (NoFactoryError)
```

The `__signature__` fix was necessary, not defensive. `provider/make_factory.py`
reads **both**:

```python
params = signature(raw_source).parameters  # line 342
hints = get_type_hints(source, include_extras=True)  # line 346
```

and splits them into `dependencies` / `kw_dependencies` by parameter *kind*.
Setting `__annotations__` alone would have left dishka seeing one `**kwargs`
parameter and no dependencies at all.

## 1. `Has` and `when=`, instead of reading dishka's internals

The sketch's `provided_scopes()` walks `Provider.factories` / `.aliases` /
`.context_vars` to decide whether an optional dependency is available. That is
dishka internals, and I flagged it as the fragile part. It has a supported
replacement.

`provide()`, `alias()` and `Provider()` all take `when: BaseMarker | None`, and
`Has(X)` is a marker meaning "X is available in the graph". Markers compose with
`~`, `|` and `&`.

```python
provider.provide(with_paths, provides=StorageWidget, when=Has(Paths))
provider.provide(without_paths, provides=StorageWidget, when=~Has(Paths))
```

Verified both directions: with `Paths` registered the wired variant is built,
without it the degraded one.

Applying it exposed a problem with that shape, though. Registering variants of
the *component* is `2**N` in its number of optional parameters. Registering one
pair per optional *type* is linear, and lets the component keep `X | None` as a
genuine dependency:

```python
provider.alias(source=X, provides=Optional[X], when=Has(X))
provider.provide(returns_none, provides=Optional[X], when=~Has(X))
```

`Optional[X]` works as a dishka key - verified with two independent optionals
across all four present/absent combinations. So a component is registered once
no matter how many optional collaborators it has.

**Applied.** `provided_scopes` is gone; `_factories.register_optionals` does
this, and `factory()` no longer needs to know what the rest of the graph
offers.

## 2. `activate` + `Marker`, for frontend variance

A user-defined marker whose truth is decided by a function evaluated during
graph build:

```python
Qt = Marker("qt")

provider.provide(build_qt_view, provides=View, when=Qt)
provider.provide(build_web_view, provides=View, when=~Qt)


class Activation(Provider):
    @activate(Qt)
    def is_qt(self) -> bool:
        return config["frontend"] == "pyqt"
```

Verified both branches. This is a better answer than `AppContainer[Qt]` for the
part of frontend selection that happens at runtime: the generic parameter is a
static claim, an activator is a runtime decision, and `_FRONTEND_CONTAINERS`
(the dotted-path string dict in `container.py`) is neither. They are not
exclusive - the generic still buys the static check.

Also the natural home for "this component only exists when that device does".

## 3. `recursive=True`

```
:param recursive: register dependencies as factories as well
```

`provide(SomeClass, recursive=True)` registers the class *and* its constructor
dependencies. This is the implicit registration I said Option 3 could offer and
dishka could not - it can. It weakens the argument for the `@service` decorator
sugar: for a plain service graph, one recursive registration covers it.

Worth using deliberately rather than by default, since implicit construction
fails badly on a mistyped annotation.

## 4. `AnyOf` and `WithParents`

`AnyOf[A, B]` as `provides=` registers one factory under several keys, and
`WithParents[X]` registers under `X` and its bases. The sketch's
`_alias_unique()` makes a separate `alias()` call per component; `AnyOf` folds
it into the original registration:

```python
components.provide(factory, provides=AnyOf[decl.key, decl.cls])
```

Cosmetic, but it removes a second pass over the declarations.

## 5. `override=True` and `ValidationSettings`

`provide(..., override=True)` is an explicit override, and
`make_container(..., validation_settings=STRICT_VALIDATION)` turns
`nothing_overridden` / `implicit_override` / `nothing_decorated` into errors.

Two uses, both real here:

- **Tests.** A test container overrides one service and gets everything else
  from the real graph. Today a mimir view test hand-builds a `VirtualContainer`
  and replays the build order.
- **Plugins.** Two bundles providing the same type is currently silent. Strict
  validation makes accidental shadowing an error and deliberate shadowing
  explicit, which matters once `providers:` sections appear in manifests.

## 6. `dishka.plotter`

`render_mermaid(container)` and `render_d2(container)`. Verified: it renders
the resolved graph, including the synthesized factories, with component names
intact.

redsun already reports `connections`, `subscriptions` and `unconnected` for the
signal layer. This is the same idea for the dependency layer, free, and the
project's docs already render Mermaid natively.

## 7. `code_tools/factory_compiler.py`

dishka compiles resolution into generated code rather than interpreting the
graph per `get()`. Two consequences: synthesized factories are not a
performance concern, and errors surface at compile time rather than at first
use, which is closer to the eager validation the design wanted.

## 8. `TypeForm` instead of `Any`

PEP 747, available now from `typing_extensions`. The sketch passes type
expressions everywhere and annotates them `Any`:

```python
def optional_arg(hint: Any) -> Any | None: ...
def injectable(cls: type, cfg: dict[str, Any]) -> dict[str, Any]: ...


available: Mapping[Any, AppScope]
```

Every one of those is a type expression, which is exactly what `TypeForm[Any]`
describes. Checked in `genprobe4.py` against all three checkers - **mypy,
pyrefly and ty all agree**:

- `int`, `MotorReadings` (a `NewType`), `dict[str, float]`, `int | None`,
  `Annotated[int, "meta"]` and `list[int] | None` all assign cleanly to
  `TypeForm[Any]`;
- `bad: TypeForm[Any] = 42` is an error in all three;
- return types reveal as `TypeForm[Any] | None`, not `Any`.

So this is not cosmetic. Under `strict`, `Any` silently accepts a wrong value
at every one of these call sites; `TypeForm` does not. It needs
`typing_extensions` at runtime, which redsun already depends on.

**Action: a mechanical pass replacing `Any` with `TypeForm[Any]` wherever a
type expression is meant, in `_factories.py`, `_declarations.py` and
`_provides.py`.**

## Not applicable

- `Component` / `FromComponent` - namespacing, already rejected: default
  isolation would force presenter authors to annotate cross-component lookups.
- `from_context` / `HasContext` - context values at scope entry. `name` is
  bound into the factory instead, which needs no context.
- `FromDishka` + `@inject` - call-time injection for framework handlers. No
  use here; slots receive signal payloads, not dependencies.
- `decorate` - wrapping a resolved dependency. Nothing wants it yet, though it
  is where a Qt thread-affinity wrapper would go if that ever became automatic.
