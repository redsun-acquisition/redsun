"""Base classes for redsun devices."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from bluesky.protocols import Configurable, HasName, HasParent

if TYPE_CHECKING:
    from bluesky.protocols import Descriptor, Reading


@runtime_checkable
class PDevice(HasName, HasParent, Configurable[Any], Protocol):  # pragma: no cover
    """Minimal required protocol for a recognizable device in Redsun."""


class Device(PDevice, abc.ABC):
    """Base class for devices.

    Users may subclass from this device and implement their own
    configuration properties and methods.

    Parameters
    ----------
    name : str
        Name of the device. Serves as a unique identifier for the object created from it.
    kwargs : Any, optional
        Additional keyword arguments for device subclasses.
    """

    @abc.abstractmethod
    def __init__(self, name: str, /, **kwargs: Any) -> None:
        self._name = name
        super().__init__(**kwargs)

    @abc.abstractmethod
    def describe_configuration(self) -> dict[str, Descriptor]:
        """Provide a description of the device configuration.

        Subclasses should override this method to provide their own
        configuration description compatible with the Bluesky event model.

        Returns
        -------
        dict[str, Descriptor]
            A dictionary with the description of each field of the device configuration.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def read_configuration(self) -> dict[str, Reading[Any]]:
        """Provide a description of the device configuration.

        Subclasses should override this method to provide their own
        configuration reading compatible with the Bluesky event model.

        Returns
        -------
        dict[str, Reading[Any]]
            A dictionary with the reading of each field of the device configuration.
        """
        raise NotImplementedError

    @property
    def name(self) -> str:
        """The name of the device, serving as a unique identifier."""
        return self._name

    @property
    def parent(self) -> None:
        """Parent of the device. Always returns None for compliance with [`HasParent`]() protocol."""
        return None
