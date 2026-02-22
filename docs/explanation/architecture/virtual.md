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

    mySignal: Signal()
    myOtherSignal: Signal(int)

    my_provider: dict[str, Any] = {}

    def my_callback(name: str, document: Document) -> None
        # a callback a RunEngine can consume

    def my_other_callback(name: str, document: Document) -> None
        # a second callback from the same owner

    def register_providers(self, container: VirtualContainer) -> None:
        # register a signal via "register signals", which can be accessed via
        # container.signals["MyComponent"]["mySignal"]
        container.register_signals(self)

        # you can also provide an alias for the component to be cached
        container.register_signals(self, "my-component")

        # you can selectively specify which signal to expose via the "only" keyword
        # and provide an iterable object containing names matching the signal attributes
        # you wish to register, hiding the others
        container.register_signals(self, only=["mySignal"])

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

    def my_slot(self) -> None:
        ...

    def inject_dependencies(self, container: VirtualContainer) -> None:
        # get the currently cached signals so you can connect them
        # to your own slots, to provide event-based communication
        # between components; be sure to handle the case
        # where the component might not be existent
        container.signals["MyComponent"]["MySignal"].connect(self.my_slot)

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
