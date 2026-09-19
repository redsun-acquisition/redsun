# Virtual container

When an application is constructed, `redsun` creates a [`VirtualContainer`][redsun.virtual.VirtualContainer], shared by every component. It holds:

- the [`psygnal.Signals`][psygnal.Signal] components register;
- `bluesky` callbacks consuming the documents a `RunEngine` produces while running a plan;
- any other object a component chooses to share, so each component decides what to expose and what to look up.

It also exposes the application-level fields of the configuration file, described in [`RedSunConfig`][redsun.virtual.RedSunConfig].

## Provider components

A component sharing any of these implements the [`IsProvider`][redsun.virtual.IsProvider] protocol by adding this method:

```python
from typing import Any

from dependency_injector import providers
from event_model.documents import Document
from psygnal import Signal

from redsun.virtual import VirtualContainer


class MyComponent:
    my_signal = Signal()
    my_other_signal = Signal(int)

    my_provider: dict[str, Any] = {}

    def my_callback(self, name: str, document: Document) -> None:
        """A callback a RunEngine can consume."""

    def my_other_callback(self, name: str, document: Document) -> None:
        """A second callback from the same owner."""

    def register_providers(self, container: VirtualContainer) -> None:
        # register a signal via "register signals", which can be accessed via
        # container.signals["MyComponent"]["my_signal"]
        container.register_signals(self)

        # you can also provide an alias for the component to be cached
        container.register_signals(self, "my-component")

        # you can selectively specify which signal to expose via the "only" keyword
        # and provide an iterable object containing names matching the signal attributes
        # you wish to register, hiding the others
        container.register_signals(self, only=["my_signal"])

        # you can register your callbacks; by default the owner's name attribute
        # is used as the registry key; if your component subclasses DocumentRouter
        # directly, it is accepted as-is without signature inspection since the
        # interface is guaranteed by the base class
        container.register_callbacks(self)

        # you can override the registry key with an explicit name
        container.register_callbacks(self, name="my-callback")

        # if you need to expose more than one callback from the same owner,
        # use the callback_map parameter; each entry is registered independently
        # under its own key, and the owner-level name is ignored
        container.register_callbacks(
            self,
            callback_map={
                "live-data": self.my_callback,
                "scan-meta": self.my_other_callback,
            },
        )

        # you can dynamically register objects the other components can get access to,
        # using the dependency_injector.providers module
        container.my_object = providers.Object(self.my_provider)
```

[`python-dependency-injector`](https://python-dependency-injector.ets-labs.org/index.html) has many more provider kinds than `Object`; see its documentation.

## Typed provider keys

Identify a shared object by a key, not by an attribute name. A key is a
[`ProviderKey`][redsun.virtual.ProviderKey], declared in the package owning the
type it identifies:

```python
import dependency_injector.providers as dip

SHUTTER = dip.Dependency(instance_of=Shutter)
```

The producer binds it and the consumer resolves it:

```python
class ShutterPresenter:
    def register_providers(self, container: VirtualContainer) -> None:
        container.provide(SHUTTER, self._shutter)


class ShutterView:
    def inject_dependencies(self, container: VirtualContainer) -> None:
        # required: raises KeyError if nothing provided it
        shutter = container.require(SHUTTER)

        # optional: None when this application declares no shutter presenter
        maybe = container.try_require(SHUTTER)
```

Both sides are typed: to a type checker `require(SHUTTER)` is a `Shutter`, and
`provide` rejects a wrong value both statically and through the key's
`instance_of`.

A key names a binding but does not hold one. Each container keeps its own, so
two applications in one process never see each other's objects.

!!! note

    Use keys for anything new. The attribute form above still works, but it is
    untyped on both sides and cannot express an optional collaborator.

## Injected components

A component retrieves objects other components provided by implementing the [`IsInjectable`][redsun.virtual.IsInjectable] protocol.

```python
from redsun.virtual import VirtualContainer
from dependency_injector import providers
from event_model.documents import Document


class MyOtherComponent:
    def my_slot(self) -> None: ...

    def inject_dependencies(self, container: VirtualContainer) -> None:
        # get the currently available callbacks so you can consume RunEngine documents;
        # this is useful when your component contains a RunEngine itself and you wish
        # to dispatch documents to other components
        callback = container.callbacks["my-callback"]
        self.engine.subscribe(callback)

        # get any object registered by other components
        object_from_component = container.my_object()
```

!!! note

    An object registered as `container.my_object = providers.Object()`, or
    through any other provider, carries no type other components can see. Its
    author must document what it is and what type it has.

## Wiring

Components do not connect their own signals. A component states what it
offers, and the application states what is connected:

- a signal is offered by declaring it, as a plain attribute or as a member of a
  [`SignalGroup`][psygnal.SignalGroup];
- a method is offered by marking it with [`slot`][redsun.virtual.slot], which
  makes its name and signature part of the component's public API;
- the application connects them, in
  [`AppContainer.wire`][redsun.containers.container.AppContainer.wire] or in the
  `wiring` section of its configuration file. Both call
  [`VirtualContainer.connect`][redsun.virtual.VirtualContainer.connect], which
  records the link so it can be reported and released.

```python
from redsun.virtual import slot


class MyComponent:
    my_signal = Signal(int)


class MyOtherComponent:
    @slot
    def my_slot(self, value: int) -> None: ...
```

=== "Container class"

    ```python
    class MyApp(AppContainer):
        producer = declare_presenter(MyComponent)
        consumer = declare_view(MyOtherComponent)

        def wire(self) -> None:
            self.connect(self.producer.my_signal, self.consumer.my_slot)
    ```

=== "Configuration file"

    ```yaml
    wiring:
      - from: producer.my_signal
        to: consumer.my_slot
    ```

`psygnal` validates signatures when connecting: it always checks the argument
count, and checks argument types too when the signal names them
(`Signal(FrameBatch)` rather than `Signal(object)`).

Device signals are the one channel outside `psygnal`.
[`subscribe`][redsun.virtual.VirtualContainer.subscribe] puts them under the
same rules: a marked slot, a thread affinity from the component, and a record
`disconnect_all` releases. It passes each reading through a `psygnal` signal,
which is what gives an `ophyd-async` subscription a thread affinity, since
`ophyd-async` calls subscribers on whichever thread produced the reading.

The signal registry above (`register_signals` / `find_signals`) is older and
still works, but it matches names only and records nothing about what was
connected. Do not use it in new components.

See [wire components together](../../how-to/wire-components.md) for the task,
and [ADR 6](../decisions/0006-application-declared-wiring.md) for why the
application owns the connections.
