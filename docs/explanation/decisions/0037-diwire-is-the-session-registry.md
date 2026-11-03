# 37. diwire is the session registry

Date: 2026-11-03

## Status

Accepted

## Context

A session builds its components out of a table of values it fills as the
build goes on: the framework values it provides itself, such as
`SessionConfig`, every component it builds, and every value a component
shares with `provides`. That table was an `in-n-out` `Store`, although only
`app-model`, which fills the commands of a Qt application, needs `in-n-out`.
Every session depended on it, Qt or not.

Two directions `redsun` wants to take need a table that belongs to one session
and nothing else. A web frontend would fill its request handlers from the same
values the components were built from, and a worker process running a heavy
presenter would build a table of its own from values sent to it. `in-n-out`
keeps a global store next to the named ones, and it answers a request for a
subclass with a value registered under its base class, so what a component
receives depends on more than what it asked for.

Two dependency injection libraries were weighed for the new table:

- `diwire` builds a container that takes registrations at any time, and
  refuses a key nobody registered when it is created with
  `MissingPolicy.ERROR`. It has no dependencies of its own.
- `wireup` checks its container once, when it is created from a complete
  list, and takes nothing afterwards.

A session registers values as it builds them and carries on when a component
fails, so it cannot give `wireup` a complete list up front, and `diwire` was
chosen.

## Decision

- `redsun.injection.Registry` wraps one `diwire` `Container`, one per session,
  through `diwire`'s public API only. A value is registered as a factory
  called on each request, as `in-n-out` called a provider each time.
- A key holds one value. A second registration under a key raises
  `RegistrationError` naming both owners, and the build stops. A component
  sharing a framework key such as `SessionConfig`, or the class of a
  component declared once, is refused the same way.
- Every key is registered in the registry step, before any component is
  built: each component's name, its class when the class is declared once,
  and the return type of each of its `provides` methods, all read from the
  declarations. Each factory returns the value the build fills in later, or
  `None` until then, and a `None` counts as not answered. `diwire` throws
  away its compiled graph on each registration, so registering components
  as they were built made it compile once per component: 40 presenters took
  1.8 s. Registered first, they take 0.12 s and one compile, and each key
  adds about 1 ms; plain methods and properties add nothing.
- A lookup matches its key exactly. `X | None` is answered by the value
  registered under `X`, because the build turns every parameter with a
  default into that form; nothing else falls back to another key. A union
  of several types that contains `None`, such as `A | B | None`, is optional:
  the parameter keeps its default.
- `app-model` reads the registry through `RegistryStore`, an `in-n-out` `Store`
  whose providers come from the registry, so nothing is registered on
  `in-n-out` itself.
- Once the build has sealed, a protocol question from outside the build, such
  as a command parameter typed with a protocol, is answered by matching built
  components by shape each time it is asked, as `setup` is answered
  (ADR 17).
- A hook in `diwire` that would let the container ask `redsun` about a key
  nobody registered was left for later. It only saves a future web frontend
  one step when it starts.

A frontend that shares the session's table with an application of its own
overrides the method returning it, as `QtSession` does for its `app-model`
application. `RegistryStore` is internal to `redsun.qt`.

Before, in `QtSession`:

```python
def make_store(self) -> Store:
    return self.model.injection_store
```

After, in `QtSession`:

```python
def make_registry(self) -> Registry:
    registry = super().make_registry()
    cast("RegistryStore", self.model.injection_store).registry = registry
    return registry
```

A component asking for a subclass of what another component shares now gets
nothing.

```python
class MyStage(Stage): ...


class MyController:
    @provides
    def stage(self) -> Stage: ...


class MyView:
    def setup(self, stage: MyStage | None = None) -> None: ...
```

Under `in-n-out`, `MyView.setup` received the `Stage` shared by
`MyController`, although it asked for `MyStage`. Under the registry it
receives `None`, because nothing is registered under `MyStage`.

## Consequences

- `in-n-out` moves to the `qt-common` extra, and the core no longer imports
  it. Code that imports `in_n_out` without the Qt extra installs it itself.
- `BuildableSession.make_store` becomes `make_registry`, which returns a
  `Registry`.
- A session that registered one key twice, which `in-n-out` allowed, stops
  building in the registry step, before any component is built, and names
  both owners. A component that would have failed to build still clashes.
- A component asking for a subclass or for a union `A | B` no longer receives
  a value registered under a base class or under one member of the union.
  With a default, `A | B | None` keeps it.
- A session builds about three times slower than under `in-n-out`, which
  compiles nothing: 0.12 s against 0.04 s for 40 presenters.
- A command can ask a protocol question once the build has sealed.
