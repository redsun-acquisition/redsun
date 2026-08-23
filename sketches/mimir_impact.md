# What this would do to redsun-mimir

Read: `providers.py`, all six presenters, all six views, `configurations/_full_simulation.py`,
`full_configuration.yaml`, `redsun.yaml`, `tests/test_presenters.py`, `tests/test_views.py`.

## The finding that changes a design decision

`providers.py` declares eleven keys. Four of them have the identical underlying
type `dict[str, Reading[Any]]`:

```python
DETECTOR_READINGS: ProviderKey[dict[str, Reading[Any]]] = dip.Dependency(
    instance_of=dict
)
MOTOR_READINGS: ProviderKey[dict[str, Reading[Any]]] = dip.Dependency(instance_of=dict)
LIGHT_CONFIGURATION: ProviderKey[dict[str, Reading[Any]]] = dip.Dependency(
    instance_of=dict
)
STATED_CONFIGURATION: ProviderKey[dict[str, Reading[Any]]] = dip.Dependency(
    instance_of=dict
)
```

and four more share `dict[str, Descriptor]`. A type-keyed container cannot tell
them apart, so `NewType` is **mandatory** here, not an optimisation for the
duplicate-instance case.

That is not a cost. `instance_of=dict` validates nothing at all - every one of
those eight keys accepts every dict - so the current runtime check is
decorative and the type parameter is upheld only by the annotation. `NewType`
is checked statically, by the type checker, at every provide and every consume:

```python
MotorReadings = NewType("MotorReadings", dict[str, Reading[Any]])
```

Eleven keys, eleven mechanical replacements, strictly stronger checking.

## Breakage, by kind

### 1. `providers.py` - rewritten, 1:1

`ProviderKey[X] = dip.Dependency(instance_of=...)` becomes `NewType`. Same
count, same names, same docstrings. The module keeps its purpose: it is still
where the bundle declares what it shares.

### 2. `register_providers` - deleted from all five presenters that have it

The pattern is always "compute a snapshot from my devices and bind it". It
becomes a factory in the bundle's own `Provider`:

```python
class MimirProviders(Provider):
    scope = Scope.APP

    @provide
    def motor_readings(self, motor_ctrl: MotorPresenter) -> MotorReadings:
        return MotorReadings(motor_ctrl.devices_readings())
```

This is where the phase ordering stops being something anyone maintains.
`MotorView` asks for `MotorReadings`, which needs `MotorPresenter`, so the
presenter is built first - dishka derives that, and the "presenters before
views" rule in `AppContainer.build` becomes unnecessary rather than merely
automated.

Depends on the plain-class alias, since each of these presenters is declared
exactly once.

### 3. `inject_dependencies` - deleted from every view, moved for one presenter

Views: the body becomes constructor parameters. `MotorView` is the
representative case.

```python
# before
def __init__(self, name: str, /, step_size: float = 10.0) -> None: ...
def register_providers(self, container):
    container.register_signals(self)


def inject_dependencies(self, container):
    self.setup_ui(
        container.require(MOTOR_READINGS), container.require(MOTOR_DESCRIPTION)
    )
    for readback in container.require(MOTOR_READBACKS).values():
        container.subscribe(readback, self.update_setpoint)


# after
def __init__(
    self,
    name: str,
    /,
    bus: VirtualContainer,
    readings: MotorReadings,
    description: MotorDescription,
    readbacks: MotorReadbacks,
    step_size: float = 10.0,
) -> None:
    ...
    self.setup_ui(readings, description)
    for readback in readbacks.values():
        bus.subscribe(readback, self.update_setpoint)
```

`register_providers` goes entirely: every mimir view uses it only for
`container.register_signals(self)`, which the framework should do for every
built component without being asked.

The comment in `MotorView.inject_dependencies` - *"the subscription is made
here rather than in wire() because subscribing delivers the current reading at
once, and the labels it writes to must exist by then"* - stops being a caveat.
In `__init__` the labels are built two statements earlier.

### 4. `AcquisitionPresenter.inject_dependencies` - resolved by a scope, see `late_injection.py`

Superseded. This section described moving the callback subscription to
`wire()`; a custom dishka scope keeps it as injection instead, with no
lifecycle hook and no author-visible marker. The description of the problem
below still holds; the conclusion does not.


```python
def inject_dependencies(self, container: VirtualContainer) -> None:
    for name, callback in container.callbacks.items():
        ...
        self.callback_tokens[name] = self.engine.subscribe(callback)
```

This reads the document-callback registry, which other components populate as
they are built. It depends on *everything having been built*, not on any
particular dependency, so dishka has nothing to order it by: put this in
`__init__` and the registry may still be empty.

It should move to `wire()`, which already runs after every component exists.
That is not a workaround - subscribing an engine to whatever callbacks the
session offers is wiring, and it is in `inject_dependencies` today only
because `wire()` had no way to express it. The bundle's `_wiring.py` is where
it belongs.

Worth confirming this is acceptable before anything is built on it. It is the
only place where losing the hook costs something.

### 5. `devices` positional - no cost

All six presenters use `devices` substantially (`self.models = devices`, plan
spec construction, per-axis iteration). They annotate `devices: DeviceMap` and
carry on. The parameter stops being mandatory for presenters that do not want
it, which in this bundle is none of them - the saving lands on `StoragePresenter`
in redsun itself.

### 6. `_full_simulation.py` and its four siblings

`from_config=` disappears from 14 of 17 declarations, because the attribute
name becomes the config key by default. Only `camera1`, `xy-motor` and
`z-motor` still need `FromConfig`, and two of those only because the YAML key
is not an identifier. `config=_CONFIG` becomes `config = _CONFIG`. The three
`declare_*` imports become one `Annotated`.

The five containers are also the place where the local `import` block inside
`build_simulation_container()` exists to defer Qt imports; that is unaffected.

### 7. `redsun.yaml` - one new optional section

```yaml
providers:
  mimir: redsun_mimir.providers:MimirProviders
```

so that a config-driven session gets the bundle's factories without the
declarative container having to name them. Without this, a YAML-only session
that uses mimir presenters cannot resolve `MotorReadings`.

### 8. Tests - net simplification

`tests/test_views.py` has a `_make_container(*bindings)` helper and two
`_build_*` helpers whose whole job is to replay the build order
(`register_providers` then `inject_dependencies`). All three disappear: a view
test constructs the view with the dicts it wants.

```python
# before
container = _make_container((MOTOR_READINGS, readings), (MOTOR_DESCRIPTION, desc))
widget.register_providers(container)
widget.inject_dependencies(container)

# after
widget = MotorView("motor", bus, readings, desc, readbacks)
```

Around fifteen call sites across `test_views.py` and `test_presenters.py`.
`test_presenters.py::test_register_providers` (three copies) becomes a test of
the provider factories instead.

## Summary

| area | change | effort |
| --- | --- | --- |
| `providers.py` | 11 keys -> 11 `NewType`s | mechanical |
| presenters | 5 `register_providers` -> one `Provider` class | small, one place |
| views | `inject_dependencies` -> ctor params | mechanical, per view |
| `AcquisitionPresenter` | callback subscription -> `wire()` | needs a decision |
| containers | `from_config=` drops from 14/17 declarations | net deletion |
| manifest | one `providers:` section | one entry |
| tests | three helpers deleted, ~15 call sites simplified | net deletion |

Nothing here needs a redsun feature that does not exist in the design. The
`AcquisitionPresenter` callback case is the only one where behaviour, not
syntax, has to move.
