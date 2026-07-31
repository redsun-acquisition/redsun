# Virtual container

At application construction, `redsun` creates a [`VirtualContainer`][redsun.virtual.VirtualContainer], a shared resource container which provides the following things:

- a registration point for [`psygnal.Signals`][psygnal.Signal] declared in your component;
- a registration point for `bluesky`-compliant callbacks to consume documents produced by a `RunEngine` during a plan execution;
- a way to dynamically registering any kind of resource to make them available to the rest of the application, giving control to the single component to expose whatever additional information it can provide or should be able to retrieve.

Additionally it provides a view of the configuration file app-level fields, described in [`RedSunConfig`][redsun.virtual.RedSunConfig].

## Provider components

Components that may wish to inject one of the above functionalities must implement the [`IsProvider`][redsun.virtual.IsProvider] protocol, by adding the following method:

```python

from redsun.virtual import VirtualContainer
from dependency_injector import providers
from event_model.documents import Document

class MyComponent:

    my_signal: Signal()
    my_other_signal: Signal(int)

    my_provider: dict[str, Any] = {}

    def my_callback(name: str, document: Document) -> None
        # a callback a RunEngine can consume

    def my_other_callback(name: str, document: Document) -> None
        # a second callback from the same owner

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
        container.register_callbacks(self, callback_map={
            "live-data": self.my_callback,
            "scan-meta": self.my_other_callback,
        })

        # you can dynamically register objects the other components can get access to,
        # using the dependency_injector.providers module
        container.my_object = providers.Object(self.my_provider)

```

[`python-dependency-injector`](https://python-dependency-injector.ets-labs.org/index.html) offers a great deal of options of what kind of resource to shared with other components. Refer to its documentation for more information.

## Injected components

Through the `VirtualContainer`, objects provided by other components may be retrieved by implementing the [`IsInjectable`][redsun.virtual.IsInjectable] protocol.

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

    Dynamically registering objects via `container.my_object = providers.Object()` or any other provider
    does not allow other components to be aware of the type hints associated with that injected object;
    it is the responsibility of component developers to document whatever object is stored in the virtual
    container and what type does it represent.

## Wiring

Signal connections are not made by the components. A component states what it
offers, and the application states what is connected:

- a signal is offered by declaring it, as a plain attribute or as a member of a
  [`SignalGroup`][psygnal.SignalGroup];
- a method is offered by marking it with [`slot`][redsun.virtual.slot], which
  makes its name and signature part of the component's public surface;
- the application connects them, in
  [`AppContainer.wire`][redsun.containers.container.AppContainer.wire] or in the `wiring`
  section of its configuration file. Both end in
  [`VirtualContainer.connect`][redsun.virtual.VirtualContainer.connect], which
  records the link so the graph can be reported and released.

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

Signature validation happens at connection time and is psygnal's: the argument
count is always checked, and the argument types are checked as well when the
signal names them (`Signal(FrameBatch)` rather than `Signal(object)`).

The signal registry above (`register_signals` / `find_signals`) predates this
and still works, but it matches on names alone and leaves no record of what was
connected. New components should not use it.

See [wire components together](../../how-to/wire-components.md) for the full
task, and [ADR 6](../decisions/0006-application-declared-wiring.md) for why the
connection lives in the application.
