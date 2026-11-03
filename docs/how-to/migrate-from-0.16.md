---
icon: lucide/arrow-right-left
---

# How to migrate from 0.16

Release 0.17 moves to `bluesky` 1.16, which renames the method a device
uses to report new readings, and builds sessions out of a registry on
`diwire` instead of an `in-n-out` store. This page gives the changes your
code may need. The [changelog](../reference/changelog.md) lists everything
else the release changed.

## An axis reports readings through `subscribe_reading`

The positioner follows an [`Axis`][redsun.utils.devices.Axis] by calling its
`subscribe_reading` method, the name `bluesky` 1.16 gives it, instead of
`subscribe`. An axis built on `ophyd-async`, such as a `StandardMovable` or a
signal, has both methods and needs no change. An axis you wrote by hand with
only `subscribe` is no longer an `Axis`, so the positioner leaves it out.
Rename the method:

```python
# 0.16
class MyAxis(StandardReadable):
    def subscribe(self, function: Callback[float]) -> None:
        self.position.subscribe_reading(function)


# now
class MyAxis(StandardReadable):
    def subscribe_reading(self, function: Callback[float]) -> None:
        self.position.subscribe_reading(function)
```

## A frontend overrides `make_registry`

A session now builds its components out of a
[`Registry`][redsun.injection.Registry], and the method a frontend overrides
to share it with an application of its own returns one. Rename the method and
return the registry the session makes:

```python
# 0.16
class MyFrontend(Session):
    def make_store(self) -> Store:
        return self.app.injection_store


# now
class MyFrontend(Session):
    def make_registry(self) -> Registry:
        registry = super().make_registry()
        self.app.registry = registry
        return registry
```

## `in-n-out` comes with the Qt extras

`redsun` no longer installs `in-n-out` on its own. The `pyqt` and `pyside`
extras still bring it, because `app-model` needs it. Code that imports
`in_n_out` in a session without either extra adds it to its own
dependencies:

```bash
uv add in-n-out
```

## One value per type

A type the session holds a value for can be shared by one owner only. A
component that shares a value under a type the session already provides,
such as `SessionConfig`, or under the class of a component declared once,
now stops the build with
[`RegistrationError`][redsun.errors.RegistrationError], which names both
owners. Share the value under a type of the component's own:

```python
# 0.16
class MyController:
    @provides
    def config(self) -> SessionConfig: ...


# now
MyConfig = NewType("MyConfig", SessionConfig)


class MyController:
    @provides
    def config(self) -> MyConfig: ...
```

## A parameter asks for the exact type

A component receives a value only under the type it was registered with. A
parameter typed with a subclass of a shared type, or with a union `A | B`,
no longer receives the value of the base class or of one member, so a
required parameter like that stops the build with "which nothing in the
session provides". Ask for the type the value is shared under. A union with a
default, such as `A | B | None = None`, keeps its default.

```python
# 0.16: received the Stage shared by another component
class MyView:
    def setup(self, stage: MyStage) -> None: ...


# now
class MyView:
    def setup(self, stage: Stage) -> None: ...
```
