from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Iterator, Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from dishka import Provider, Scope
from event_model import DocumentRouter
from event_model.documents import Document
from ophyd_async.core import Device
from psygnal import Signal, SignalGroup, SignalInstance

from redsun.aio import run_coro
from redsun.experimental.log import Loggable
from redsun.experimental.virtual._requires import Satisfying
from redsun.experimental.virtual._wiring import (
    SLOT_ATTR,
    SLOT_THREAD_ATTR,
    Connection,
    Slot,
    Subscription,
    Unconnected,
    WiringError,
    port_name,
    ports,
)

if TYPE_CHECKING:
    from bluesky.protocols import HasName
    from ophyd_async.core import SignalR

    from redsun.experimental.virtual._wiring import SlotThread

__all__ = [
    "BlueskyCallbackRegistry",
    "CallbackType",
    "DeviceMapping",
    "SessionConfig",
    "VirtualContainer",
]

# these three are dishka keys, so every name in them must resolve at runtime:
# the graph evaluates the annotation, and a TYPE_CHECKING-only import fails there
CallbackType: TypeAlias = Callable[[str, Document], None] | DocumentRouter
"""A document callback: a `DocumentRouter`, or anything callable as ``(name, doc)``."""

DeviceMapping: TypeAlias = Mapping[str, Device]
"""Every device an application built, by name.

Not ophyd-async's ``DeviceMap``, which is a device holding string-keyed
children; this is the application's own set.
"""

SignalCache: TypeAlias = dict[str, SignalInstance]
"""The signals one component declares, by attribute name."""


def validate_callback(callback: object) -> CallbackType:
    """Return *callback* unchanged if it can be called as ``(name, doc)``.

    Raises
    ------
    TypeError
        If *callback* is not callable, or its signature is incompatible
        with ``(str, Document)``.
    """
    if isinstance(callback, DocumentRouter):
        return callback

    if not callable(callback):
        raise TypeError(
            f"{callback!r} is not callable. "
            "A callback must be a DocumentRouter subclass instance or a "
            "callable accepting (str, Document) arguments."
        )

    try:
        inspect.signature(callback.__call__).bind(None, None)
    except TypeError as e:
        raise TypeError(
            f"{callback!r} is callable but its signature is not compatible "
            "with the expected (str, Document) callback interface."
        ) from e

    return callback


class BlueskyCallbackRegistry(Mapping[str, CallbackType]):
    """The bluesky document-callback registry, as a component sees it.

    A component receives this while it is being built. It may register its own
    callbacks straight away, and it may hold the mapping and read it when it
    runs. Reading it before the application has finished building raises,
    because the components after it have registered nothing yet and the answer
    would be incomplete.

    Parameters
    ----------
    registry : MutableMapping[str, CallbackType]
        The mapping every component registers into, held rather than copied so
        that a component reads what later ones added.
    ready : Callable[[], bool]
        Answers whether every component has been built. Reading the mapping
        before it answers ``True`` raises.

    Raises
    ------
    LookupError
        If read before every component exists.
    """

    def __init__(
        self, registry: MutableMapping[str, CallbackType], ready: Callable[[], bool]
    ) -> None:
        self._registry = registry
        self._ready = ready

    def register(
        self,
        owner: HasName,
        *,
        name: str | None = None,
        callback_map: dict[str, CallbackType] | None = None,
    ) -> None:
        """Register one or more document callbacks.

        Parameters
        ----------
        owner : HasName
            The component registering callbacks, and the callback itself when
            *callback_map* is ``None``.
        name : str | None
            Registry key for *owner*. Defaults to ``owner.name``; ignored when
            *callback_map* is given.
        callback_map : dict[str, CallbackType] | None
            Several callbacks from one owner, each registered under its own
            key. *owner* is then not registered itself.

        Raises
        ------
        TypeError
            If a callback is not callable or its signature is incompatible
            with ``(str, Document)``.
        """
        if callback_map is not None:
            for key, callback in callback_map.items():
                self._registry[key] = validate_callback(callback)
            return

        self._registry[name if name is not None else owner.name] = validate_callback(
            owner
        )

    def _complete(self) -> Mapping[str, CallbackType]:
        if not self._ready():
            raise LookupError(
                "the document-callback registry is not complete until every "
                "component exists. Hold this view and read it when the "
                "component runs, rather than copying it while it is built."
            )
        return self._registry

    def __getitem__(self, key: str) -> CallbackType:
        return self._complete()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._complete())

    def __len__(self) -> int:
        return len(self._complete())

    def __repr__(self) -> str:
        state = "live" if self._ready() else "pending"
        return f"BlueskyCallbackRegistry({state}, {len(self._registry)} registered)"


@dataclass(frozen=True, kw_only=True)
class SessionConfig:
    """The configuration an application was built from."""

    schema_version: float = 1.0
    frontend: str = "pyqt"
    name: str = "Redsun"
    metadata: dict[str, object] = field(default_factory=dict)


def _owner_of(signal: SignalInstance) -> object | None:
    """Return the component a signal belongs to.

    A signal declared inside a `SignalGroup` reports the group as its
    instance, so the owning component is one level further out.
    """
    instance: object | None = signal.instance
    if isinstance(instance, SignalGroup):
        return cast("object | None", instance.instance)
    return instance


class VirtualContainer(Loggable):
    """Data exchange layer for an application.

    Holds what the framework itself knows and every component may need: the
    session configuration, the signal wiring, and the document-callback
    registry. Anything specific to a component belongs to that component,
    shared with `provides`.

    Lives for the whole application, and owns its teardown: connections,
    subscriptions and everything registered with `on_release` are undone by a
    single call to `release`.
    """

    def __init__(self) -> None:
        self._config = SessionConfig()
        self._signals: dict[str, SignalCache] = {}
        self._callbacks: dict[str, CallbackType] = {}
        self._components: dict[str, object] = {}
        self._names: dict[int, str] = {}
        self._finalizers: list[Callable[[], None]] = []
        self._sealed = False
        self._links: list[tuple[SignalInstance, Callable[..., Any]]] = []
        self._connections: list[Connection] = []
        # the forwarding function is held because ophyd-async releases a
        # subscription by identity: clear_sub needs the object back
        self._subscriptions: list[
            tuple[SignalR[Any], Callable[[Any], None], SignalInstance]
        ] = []
        self._subscription_records: list[Subscription] = []
        self._registry = BlueskyCallbackRegistry(self._callbacks, lambda: self._sealed)

    def provider(self, devices: Callable[[], DeviceMapping]) -> Provider:
        """Return the framework's dependency provider.

        Everything the framework knows is registered here, and every component
        may ask for it by type. The callback registry is a live view, so it is
        available at construction like the rest and carries no ordering
        constraint of its own.
        """
        provider = Provider(scope=Scope.APP)
        provider.provide(lambda: self._config, provides=SessionConfig)
        provider.provide(devices, provides=DeviceMapping)
        provider.provide(lambda: self._registry, provides=BlueskyCallbackRegistry)
        return provider

    @property
    def config(self) -> SessionConfig:
        """The configuration this application was built from."""
        return self._config

    @property
    def schema_version(self) -> float:
        """The plugin schema version specified in the configuration."""
        return self._config.schema_version

    @property
    def frontend(self) -> str:
        """The frontend toolkit identifier specified in the configuration."""
        return self._config.frontend

    @property
    def name(self) -> str:
        """The session identity specified in the configuration."""
        return self._config.name

    @property
    def metadata(self) -> dict[str, object]:
        """The session metadata specified in the configuration."""
        return self._config.metadata

    def _set_configuration(self, config: Mapping[str, Any], name: str) -> None:
        """Set the application configuration, for use by the container.

        *name* is what the session is called when the configuration does not
        say, which the container takes from its own class.
        """
        self._config = SessionConfig(
            schema_version=config.get("schema_version", 1.0),
            frontend=config.get("frontend", "pyqt"),
            name=config.get("name", name),
            metadata=dict(config.get("metadata", {})),
        )

    def register_signals(
        self, owner: HasName, name: str | None = None, only: Iterable[str] | None = None
    ) -> None:
        """Cache the signals *owner* declares.

        Parameters
        ----------
        owner : HasName
            The component whose class signals are cached.
        name : str | None
            Registry key. Defaults to ``owner.name``.
        only : Iterable[str] | None
            Signal names to cache. Defaults to every
            [`Signal`][psygnal.Signal] declared on the class.
        """
        owner_class = type(owner)
        cache_entry = name if name is not None else owner.name

        if only is None:
            only = [
                attr
                for attr in dir(owner_class)
                if isinstance(getattr(owner_class, attr, None), Signal)
            ]

        batch: dict[str, SignalInstance] = {}
        for signal_name in only:
            descriptor = getattr(owner_class, signal_name, None)
            if isinstance(descriptor, Signal):
                batch[signal_name] = getattr(owner, signal_name)
        if batch:
            self._signals[cache_entry] = batch

    @property
    def signals(self) -> dict[str, SignalCache]:
        """The currently registered signals."""
        return dict(self._signals)

    def register_callbacks(
        self,
        owner: HasName,
        name: str | None = None,
        callback_map: dict[str, CallbackType] | None = None,
    ) -> None:
        """Register one or more document callbacks.

        Parameters
        ----------
        owner : HasName
            The component registering callbacks, and the callback itself when
            *callback_map* is ``None``.
        name : str | None
            Registry key for *owner*. Defaults to ``owner.name``; ignored when
            *callback_map* is given.
        callback_map : dict[str, CallbackType] | None
            Several callbacks from one owner, each registered under its own
            key. *owner* is then not registered itself.

        Raises
        ------
        TypeError
            If a callback is not callable or its signature is incompatible
            with ``(str, Document)``.
        """
        self._registry.register(owner, name=name, callback_map=callback_map)

    @property
    def callbacks(self) -> dict[str, CallbackType]:
        """The currently registered document callbacks."""
        return dict(self._callbacks)

    def _set_components(self, components: Mapping[str, object]) -> None:
        """Record the names built components are known by.

        Both mappings are filled in place rather than rebound: a live view
        handed to a component holds the mapping itself, and rebinding would
        leave it looking at the empty one it was given during the build.
        """
        self._components.clear()
        self._components.update(components)
        self._names.clear()
        self._names.update({id(c): name for name, c in components.items()})

    def _label(self, component: object | None) -> str:
        if component is None:
            return "<unknown>"
        return self._names.get(id(component), type(component).__name__)

    def _affinity(self, slot: Callable[..., Any], thread: SlotThread) -> SlotThread:
        declaration = getattr(slot, SLOT_ATTR, None)
        if not isinstance(declaration, Slot):
            name = getattr(slot, "__qualname__", repr(slot))
            raise WiringError(
                f"{name} is not connectable; mark it with the 'slot' decorator"
            )
        if thread is not None:
            return thread
        consumer = getattr(slot, "__self__", None)
        return declaration.thread or cast(
            "SlotThread", getattr(type(consumer), SLOT_THREAD_ATTR, None)
        )

    def connect(
        self,
        signal: SignalInstance,
        slot: Callable[..., Any],
        *,
        thread: SlotThread = None,
    ) -> Connection:
        """Connect a signal to a slot and record the link.

        Parameters
        ----------
        signal : SignalInstance
            The emitting signal.
        slot : Callable[..., Any]
            A bound method marked with [`slot`][redsun.virtual.slot]. May be a
            coroutine function.
        thread : SlotThread
            Delivery thread. Defaults to the affinity the slot declares, then
            to the one its class declares.

        Returns
        -------
        Connection
            The recorded link.

        Raises
        ------
        WiringError
            If *slot* is not marked as connectable, or if psygnal rejects the
            two signatures.
        """
        thread = self._affinity(slot, thread)
        link = Connection(
            publisher=self._label(_owner_of(signal)),
            publisher_port=signal.name or "<anonymous>",
            consumer=self._label(getattr(slot, "__self__", None)),
            consumer_port=port_name(slot),
            thread=thread,
        )
        try:
            signal.connect(slot, thread=thread)
        except (TypeError, ValueError) as e:
            raise WiringError(f"cannot connect {link}: {e}") from e

        self._links.append((signal, slot))
        self._connections.append(link)
        self.logger.debug(f"Connected {link}")
        return link

    def subscribe(
        self,
        signal: SignalR[Any],
        slot: Callable[..., Any],
        *,
        thread: SlotThread = None,
    ) -> Subscription:
        """Subscribe a slot to an ophyd-async device signal and record it.

        Delivery is marshalled through a psygnal signal, so *thread* behaves as
        it does for `connect`. This is the only way a device signal can reach a
        slot with a thread affinity: ophyd-async calls its subscribers on
        whatever thread produced the reading.

        Parameters
        ----------
        signal : SignalR[Any]
            The device signal to observe.
        slot : Callable[..., Any]
            A bound method marked with [`slot`][redsun.virtual.slot], called
            with the reading dictionary.
        thread : SlotThread
            Delivery thread. Defaults to the affinity the slot declares, then
            to the one its class declares.

        Returns
        -------
        Subscription
            The recorded subscription.

        Raises
        ------
        WiringError
            If *slot* is not marked as connectable.
        """
        thread = self._affinity(slot, thread)
        relay = SignalInstance((object,), name=signal.name)
        relay.connect(slot, thread=thread)

        def forward(reading: Any) -> None:
            relay.emit(reading)

        record = Subscription(
            source=signal.name,
            consumer=self._label(getattr(slot, "__self__", None)),
            consumer_port=port_name(slot),
            thread=thread,
        )

        async def attach() -> None:
            signal.subscribe_reading(forward)

        # ophyd-async requires a running loop to subscribe, and callers run on
        # the main thread during the build
        run_coro(attach())
        self._subscriptions.append((signal, forward, relay))
        self._subscription_records.append(record)
        self.logger.debug(f"Subscribed {record}")
        return record

    @property
    def subscriptions(self) -> list[Subscription]:
        """The device-signal subscriptions made through this container."""
        return list(self._subscription_records)

    def connect_paths(
        self, source: str, target: str, *, thread: SlotThread = None
    ) -> Connection:
        """Connect two ports addressed as ``component.port``.

        The string form of `connect`, used by the ``wiring`` section of a
        configuration file.

        Parameters
        ----------
        source : str
            Path of the emitting signal.
        target : str
            Path of the consuming slot.
        thread : SlotThread
            Delivery thread, overriding the slot and its class.

        Returns
        -------
        Connection
            The recorded link.

        Raises
        ------
        WiringError
            If either path is malformed, names a component that was not built,
            or names a port that component does not expose.
        """
        signal = self._resolve_port(source, "signal")
        slot = self._resolve_port(target, "slot")
        return self.connect(
            cast("SignalInstance", signal),
            cast("Callable[..., Any]", slot),
            thread=thread,
        )

    def _resolve_port(self, path: str, kind: str) -> object:
        """Look up the signal or slot a ``component.port`` path names."""
        component_name, _, port = path.partition(".")
        if not component_name or not port or "." in port:
            raise WiringError(f"{path!r} is not a port path; expected 'component.port'")
        component = self._components.get(component_name)
        if component is None:
            known = ", ".join(sorted(self._components)) or "none"
            raise WiringError(
                f"{path!r} names component {component_name!r}, which was not "
                f"built. Built: {known}"
            )
        surface = ports(component)
        available = surface.signals if kind == "signal" else surface.slots
        if port not in available:
            known = ", ".join(sorted(available)) or "none"
            raise WiringError(
                f"{component_name!r} exposes no {kind} named {port!r}. "
                f"Its {kind} ports: {known}"
            )
        return available[port]

    @property
    def connections(self) -> list[Connection]:
        """The links established so far."""
        return list(self._connections)

    @property
    def unconnected(self) -> Unconnected:
        """Ports of the built components that no connection reaches.

        The complement of `connections` and `subscriptions`: what a component
        offers and nothing uses.

        Raises
        ------
        WiringError
            If a component exposes two signals under one port name.
        """
        used_signals = {(c.publisher, c.publisher_port) for c in self._connections}
        used_slots = {(c.consumer, c.consumer_port) for c in self._connections}
        used_slots |= {
            (s.consumer, s.consumer_port) for s in self._subscription_records
        }

        signals: list[str] = []
        slots: list[str] = []
        for name, component in self._components.items():
            surface = ports(component)
            signals += [
                f"{name}.{port}"
                for port in surface.signals
                if (name, port) not in used_signals
            ]
            slots += [
                f"{name}.{port}"
                for port in surface.slots
                if (name, port) not in used_slots
            ]
        return Unconnected(signals=signals, slots=slots)

    def satisfying(self, protocol: type) -> Satisfying:
        """Return a live view of the built components satisfying *protocol*."""
        return Satisfying(protocol, self._components, lambda: self._sealed)

    def on_release(self, finalizer: Callable[[], None]) -> None:
        """Register a callable to run when the application is torn down.

        Finalizers run in reverse registration order, so a dependency is
        released after whatever was built from it.
        """
        self._finalizers.append(finalizer)

    def release(self) -> None:
        """Tear the application down.

        Connections go first, so nothing is delivered to a component that is
        already finalizing. Every finalizer runs even if an earlier one
        raised.

        Raises
        ------
        ExceptionGroup
            Carrying whatever the finalizers raised.
        """
        self._sealed = False
        self.disconnect_all()

        errors: list[Exception] = []
        while self._finalizers:
            try:
                self._finalizers.pop()()
            except Exception as e:  # noqa: BLE001 - one failure must not strand the rest
                errors.append(e)

        self._callbacks.clear()
        self._signals.clear()
        self._components.clear()
        self._names.clear()
        if errors:
            raise ExceptionGroup("errors while releasing the application", errors)

    def _seal(self) -> None:
        """Mark the build complete, making the live views readable."""
        self._sealed = True

    def disconnect_all(self) -> None:
        """Undo every connection and subscription made through this container."""
        for signal, slot in self._links:
            signal.disconnect(slot, missing_ok=True)
        self._links.clear()
        self._connections.clear()

        async def release(signal: SignalR[Any], forward: Callable[[Any], None]) -> None:
            signal.clear_sub(forward)

        for device_signal, forward, relay in self._subscriptions:
            run_coro(release(device_signal, forward))
            relay.disconnect()
        self._subscriptions.clear()
        self._subscription_records.clear()
