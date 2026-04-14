"""Base classes for redsun devices."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from bluesky.protocols import Configurable, HasName, HasParent

if TYPE_CHECKING:
    from collections.abc import Iterator

    from bluesky.protocols import Descriptor, Reading, SyncOrAsync

_DEVICE_INTERNALS: frozenset[str] = frozenset({"_name", "_parent", "_child_devices"})


@runtime_checkable
class PDevice(HasName, HasParent, Configurable[Any], Protocol):  # pragma: no cover
    """Minimal required protocol for a recognizable device in Redsun.

    Extends [`HasName`][bluesky.protocols.HasName],
    [`HasParent`][bluesky.protocols.HasParent], and
    [`Configurable`][bluesky.protocols.Configurable] with
    [`set_name`][], which is required for devices that participate in a
    parent/child hierarchy (the parent calls `child.set_name()` on
    assignment). Structurally compatible with `ophyd_async.core.Device`.
    """

    def set_name(self, name: str) -> None:
        """Update the device name."""
        ...


@runtime_checkable
class HasChildren(Protocol):
    """Structural protocol for devices that expose a child-device iterator.

    Satisfied by any object that implements
    [`children()`][redsun.device.Device.children].
    [`Device`][redsun.device.Device] satisfies this protocol; so does any
    ophyd-async device that provides the same method.
    """

    def children(self) -> Iterator[tuple[str, Device]]:
        """Iterate over registered child devices.

        Yields
        ------
        tuple[str, Device]
            ``(attribute_name, child_device)`` pairs.
        """
        ...


class Device(PDevice, abc.ABC):
    """Base class for devices.

    Subclasses that expose attributes as [`AttrR`][redsun.device.AttrR] /
    [`AttrRW`][redsun.device.AttrRW] signals do not need to override
    [`describe_configuration`][] or [`read_configuration`][]; the
    default implementations return empty dicts. Subclasses that manage
    configuration manually should override both methods. Either sync or
    async implementations are accepted.

    Child devices are registered automatically: when a `Device` instance
    is assigned to an attribute on another `Device`, it is recorded in
    [`children`][] and its [`parent`][] is set. Name changes made via
    [`set_name`][] propagate recursively to all children and to any
    attribute that carries a `set_name()` method (e.g.
    [`SoftAttrRW`][redsun.device.SoftAttrRW]).

    For attrs-decorated subclasses (`@define`), use
    `on_setattr=setters.NO_OP` to prevent attrs from generating its own
    `__setattr__` that would shadow this class's implementation.

    Parameters
    ----------
    name : str
        Name of the device. Serves as a unique identifier for the object
        created from it.
    kwargs : Any, optional
        Additional keyword arguments for device subclasses.
    """

    _name: str
    _parent: Device | None
    _child_devices: dict[str, Device]

    @abc.abstractmethod
    def __init__(self, name: str, /, **kwargs: Any) -> None:
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_parent", None)
        object.__setattr__(self, "_child_devices", {})
        super().__init__(**kwargs)

    def __setattr__(self, attr: str, value: Any) -> None:
        object.__setattr__(self, attr, value)
        if attr in _DEVICE_INTERNALS or not hasattr(self, "_child_devices"):
            return
        if isinstance(value, Device):
            object.__setattr__(value, "_parent", self)
            self._child_devices[attr] = value
            if self._name:
                value.set_name(f"{self._name}-{attr}")
        elif self._name and hasattr(value, "set_name") and callable(value.set_name):
            value.set_name(f"{self._name}-{attr}")

    def set_name(self, name: str) -> None:
        """Update the device name and propagate to all children.

        Sets [`name`][] on this device, then recursively calls
        `set_name()` on every registered child [`Device`][] and on every
        non-internal attribute that carries a `set_name()` method (e.g.
        [`SoftAttrRW`][redsun.device.SoftAttrRW] fields).

        Parameters
        ----------
        name : str
            New fully-qualified name for this device.
        """
        object.__setattr__(self, "_name", name)
        for attr, child in self._child_devices.items():
            child.set_name(f"{name}-{attr}")
        for attr, value in vars(self).items():
            if attr.startswith("_") or attr in self._child_devices:
                continue
            if hasattr(value, "set_name") and callable(value.set_name):
                value.set_name(f"{name}-{attr}")

    def children(self) -> Iterator[tuple[str, Device]]:
        """Iterate over registered child devices.

        Yields
        ------
        tuple[str, Device]
            ``(attribute_name, child_device)`` pairs in insertion order.
        """
        yield from self._child_devices.items()

    def describe_configuration(self) -> SyncOrAsync[dict[str, Descriptor]]:
        """Return a description of the device configuration.

        The default implementation returns an empty dict, appropriate for
        devices that expose configuration through typed attributes
        ([`AttrR`][redsun.device.AttrR] / [`AttrRW`][redsun.device.AttrRW])
        rather than through this method directly.

        Returns
        -------
        SyncOrAsync[dict[str, Descriptor]]
            A dictionary with the descriptor of each configuration field,
            or an awaitable that resolves to one.
        """
        return {}

    def read_configuration(self) -> SyncOrAsync[dict[str, Reading[Any]]]:
        """Return the current values of the device configuration.

        The default implementation returns an empty dict, appropriate for
        devices that expose configuration through typed attributes
        ([`AttrR`][redsun.device.AttrR] / [`AttrRW`][redsun.device.AttrRW])
        rather than through this method directly.

        Returns
        -------
        SyncOrAsync[dict[str, Reading[Any]]]
            A dictionary with the current reading of each configuration
            field, or an awaitable that resolves to one.
        """
        return {}

    @property
    def name(self) -> str:
        """The name of the device, serving as a unique identifier."""
        return self._name

    @property
    def parent(self) -> Device | None:
        """Parent device, or ``None`` for root devices."""
        return self._parent
