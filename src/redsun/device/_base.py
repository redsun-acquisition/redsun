"""Base classes for redsun devices."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from bluesky.protocols import Configurable, HasName, HasParent

if TYPE_CHECKING:
    from bluesky.protocols import Descriptor, Reading, SyncOrAsync


@runtime_checkable
class PDevice(HasName, HasParent, Configurable[Any], Protocol):  # pragma: no cover
    """Minimal required protocol for a recognizable device in Redsun."""


class Device(PDevice, abc.ABC):
    """Base class for devices.

    Users may subclass from this device and implement their own
    configuration properties and methods.

    Subclasses that expose attributes as :class:`~redsun.device.AttrR` /
    :class:`~redsun.device.AttrRW` signals do not need to override
    :meth:`describe_configuration` or :meth:`read_configuration`; the
    default implementations return empty dicts.  Subclasses that manage
    configuration manually should override both methods.  Either sync or
    async implementations are accepted.

    Parameters
    ----------
    name : str
        Name of the device. Serves as a unique identifier for the object
        created from it.
    kwargs : Any, optional
        Additional keyword arguments for device subclasses.
    """

    @abc.abstractmethod
    def __init__(self, name: str, /, **kwargs: Any) -> None:
        self._name = name
        super().__init__(**kwargs)

    def describe_configuration(self) -> SyncOrAsync[dict[str, Descriptor]]:
        """Return a description of the device configuration.

        The default implementation returns an empty dict, which is
        appropriate for devices that expose configuration through typed
        attributes (:class:`~redsun.device.AttrR` /
        :class:`~redsun.device.AttrRW`) rather than through this method
        directly.

        Subclasses that manage configuration manually should override
        this method and return a dict compatible with the Bluesky event
        model.  Both sync and async overrides are accepted.

        Returns
        -------
        SyncOrAsync[dict[str, Descriptor]]
            A dictionary with the descriptor of each configuration field,
            or an awaitable that resolves to one.
        """
        return {}

    def read_configuration(self) -> SyncOrAsync[dict[str, Reading[Any]]]:
        """Return the current values of the device configuration.

        The default implementation returns an empty dict, which is
        appropriate for devices that expose configuration through typed
        attributes (:class:`~redsun.device.AttrR` /
        :class:`~redsun.device.AttrRW`) rather than through this method
        directly.

        Subclasses that manage configuration manually should override
        this method and return a dict compatible with the Bluesky event
        model.  Both sync and async overrides are accepted.

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
    def parent(self) -> None:
        """Parent of the device. Always returns None for compliance with [`HasParent`]() protocol."""
        return None
