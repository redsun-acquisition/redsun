from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    TypeAlias,
    TypeVar,
    cast,
)

import dependency_injector.containers as dic
import dependency_injector.providers as dip
from event_model import DocumentRouter
from event_model.documents import Document
from psygnal import Signal, SignalGroup, SignalInstance

from redsun.log import Loggable
from redsun.virtual._wiring import (
    SLOT_ATTR,
    SLOT_THREAD_ATTR,
    Connection,
    Slot,
    SlotThread,
    WiringError,
    port_name,
    ports,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from bluesky.protocols import HasName

    from redsun.virtual._config import RedSunConfig

K = TypeVar("K")
V = TypeVar("V")
T = TypeVar("T")

ProviderKey: TypeAlias = dip.Dependency[T]
"""A typed key identifying an object shared through the container."""

CallbackType: TypeAlias = Callable[[str, Document], None] | DocumentRouter
"""Type alias for document callback functions."""

__all__ = ["Connection", "ProviderKey", "Signal", "VirtualContainer"]

SignalCache: TypeAlias = dict[str, SignalInstance]
"""Cache type for storing signal instances registered from component classes."""


@dataclass(frozen=True, kw_only=True)
class _FrozenConfig:
    """Frozen configuration dataclass."""

    schema_version: float
    frontend: str
    session: str
    metadata: dict[str, object]


def _owner_of(signal: SignalInstance) -> object | None:
    """Return the component a signal belongs to.

    A signal declared inside a `SignalGroup` reports the group as its
    instance, so the owning component is one level further out.
    """
    instance: object | None = signal.instance
    if isinstance(instance, SignalGroup):
        return cast("object | None", instance.instance)
    return instance


class VirtualContainer(dic.DynamicContainer, Loggable):
    """Data exchange and dependency injection layer.

    `VirtualContainer` is a [`DynamicContainer`][dependency_injector.containers.DynamicContainer]
    that also acts as a runtime signal bus and data sharing layer for an application.
    """

    def __init__(self) -> None:
        super().__init__()
        # instance-scoped providers: class-level providers would be shared
        # across every container in the process, leaking config, signal,
        # and callback registrations between containers
        self._signals = dip.Factory(dict[str, SignalCache])
        self._callbacks = dip.Factory(dict[str, CallbackType])
        self._config = dip.Singleton(_FrozenConfig)
        self._components: dict[str, object] = {}
        self._names: dict[int, str] = {}
        self._links: list[tuple[SignalInstance, Callable[..., Any]]] = []
        self._connections: list[Connection] = []
        # bindings are held here rather than through Dependency.override, which
        # mutates the key itself and would leak between containers in one process
        self._provided: dict[dip.Dependency[Any], Any] = {}

    @property
    def schema_version(self) -> float:
        """The plugin schema version specified in the configuration."""
        return self._config().schema_version

    @property
    def frontend(self) -> str:
        """The frontend toolkit identifier specified in the configuration."""
        return self._config().frontend

    @property
    def session(self) -> str:
        """The session display name specified in the configuration."""
        return self._config().session

    @property
    def metadata(self) -> dict[str, object]:
        """The session metadata specified in the configuration."""
        return self._config().metadata

    def _set_configuration(self, config: RedSunConfig) -> None:
        """Set the application configuration.

        Private for use by the application layer at build time.

        Parameters
        ----------
        config : RedSunConfig
            The application configuration to set.
        """
        self._config.set_kwargs(
            schema_version=config["schema_version"],
            frontend=config["frontend"],
            session=config.get("session", "redsun"),
            metadata=config.get("metadata", {}),
        )

    def provide(self, key: ProviderKey[T], value: T) -> None:
        """Bind *value* to *key* for this container.

        Parameters
        ----------
        key : ProviderKey[T]
            The key consumers resolve.
        value : T
            The object to share. Rebinding an already bound key replaces it.

        Raises
        ------
        TypeError
            If *value* is not an instance of the key's ``instance_of``.
        """
        if not isinstance(value, key.instance_of):
            raise TypeError(
                f"{value!r} is not an instance of "
                f"{key.instance_of.__name__}, required by {key!r}"
            )
        self._provided[key] = value

    def require(self, key: ProviderKey[T]) -> T:
        """Resolve *key*, which must be bound.

        Parameters
        ----------
        key : ProviderKey[T]
            The key to resolve.

        Returns
        -------
        T
            The bound value.

        Raises
        ------
        KeyError
            If nothing bound *key*. Providers are bound during
            ``register_providers``, so a key read before that phase is unbound
            even when the owning component is present.
        """
        try:
            return cast("T", self._provided[key])
        except KeyError:
            raise KeyError(
                f"nothing provided {key!r}; the component that owns it is "
                "either absent from this application or has not run "
                "'register_providers' yet"
            ) from None

    def try_require(self, key: ProviderKey[T]) -> T | None:
        """Resolve *key*, or return ``None`` if nothing bound it.

        Parameters
        ----------
        key : ProviderKey[T]
            The key to resolve.

        Returns
        -------
        T | None
            The bound value, or ``None`` for an optional collaborator that this
            application does not include.
        """
        return cast("T | None", self._provided.get(key))

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
        if name is not None:
            cache_entry = name
        else:
            cache_entry = owner.name

        if only is None:
            only = [
                attr
                for attr in dir(owner_class)
                if isinstance(getattr(owner_class, attr, None), Signal)
            ]

        batch: dict[str, SignalInstance] = {}
        for signal_name in only:
            signal_descriptor = getattr(owner_class, signal_name, None)
            if isinstance(signal_descriptor, Signal):
                signal_instance = getattr(owner, signal_name)
                batch[signal_name] = signal_instance
        if batch:
            self._signals.add_kwargs(**{cache_entry: batch})

    @staticmethod
    def _validate_callback(callback: object) -> CallbackType:
        """Return *callback* unchanged if it can be called as ``(name, doc)``.

        Parameters
        ----------
        callback : object
            The object to validate.

        Returns
        -------
        CallbackType
            The validated callback.

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

    def register_callbacks(
        self,
        owner: HasName,
        name: str | None = None,
        callback_map: dict[str, CallbackType] | None = None,
    ) -> None:
        """Register one or more document callbacks.

        A callback is an ``event_model.DocumentRouter`` or any object callable
        as ``(name, doc)``.

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
                self._callbacks.add_kwargs(**{key: self._validate_callback(callback)})
            return

        cache_entry = name if name is not None else owner.name
        self._callbacks.add_kwargs(**{cache_entry: self._validate_callback(owner)})

    @property
    def callbacks(self) -> dict[str, CallbackType]:
        """The currently registered document callbacks."""
        return self._callbacks()

    @property
    def signals(self) -> dict[str, SignalCache]:
        """The currently registered signals."""
        return self._signals()

    def _set_components(self, components: Mapping[str, object]) -> None:
        """Record the names built components are known by, for the wiring report."""
        self._components = dict(components)
        self._names = {id(component): name for name, component in components.items()}

    def _label(self, component: object | None) -> str:
        if component is None:
            return "<unknown>"
        return self._names.get(id(component), type(component).__name__)

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
        declaration = getattr(slot, SLOT_ATTR, None)
        if not isinstance(declaration, Slot):
            name = getattr(slot, "__qualname__", repr(slot))
            raise WiringError(
                f"{name} is not connectable; mark it with the 'slot' decorator"
            )

        consumer = getattr(slot, "__self__", None)
        if thread is None:
            thread = declaration.thread or cast(
                "SlotThread", getattr(type(consumer), SLOT_THREAD_ATTR, None)
            )

        link = Connection(
            publisher=self._label(_owner_of(signal)),
            publisher_port=signal.name or "<anonymous>",
            consumer=self._label(consumer),
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

    def connect_paths(
        self, source: str, target: str, *, thread: SlotThread = None
    ) -> Connection:
        """Connect two ports addressed as ``component.port``.

        The string form of `connect`, used by the ``wiring`` section of a
        configuration file. A signal port is the signal's attribute name, or the
        member name when it belongs to a signal group; a slot port is the name
        the slot declares.

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
            or names a port that component does not expose. The message lists
            what does exist.
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

    def disconnect_all(self) -> None:
        """Undo every connection made through this container."""
        for signal, slot in self._links:
            signal.disconnect(slot, missing_ok=True)
        self._links.clear()
        self._connections.clear()
