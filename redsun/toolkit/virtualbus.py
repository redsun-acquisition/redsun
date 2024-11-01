"""
The `VirtualBus` is a mechanism to exchange data between different parts of the system.

The module contains two main classes: `Signal` and `VirtualBus`.

The `Signal` class is a small wrapper around `psygnal.SignalInstance` that provides additional properties to access the signal data types and description.

The `VirtualBus` class is a factory of singleton objects charged of exchanging information between different controllers via `Signals`.

`VirtualBuses` can be inter-module or intra-module, and they can be used to emit notifications, as well as carry information to other plugins and/or different RedSun modules.
"""

from abc import ABC
from functools import lru_cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Dict

from psygnal import SignalInstance

from redsun.toolkit.log import Loggable

if TYPE_CHECKING:
    from typing import Any, Tuple

__all__ = ["Signal", "VirtualBus"]


class Signal(SignalInstance):
    """Small wrapper around `psygnal.SignalInstance`."""

    def __init__(
        self, *argtypes: "Any", info: str = "RedSun signal", **kwargs: "Any"
    ) -> None:
        SignalInstance.__init__(self, signature=argtypes, **kwargs)
        self._info = info

    @property
    @lru_cache
    def types(self) -> "Tuple[type, ...]":
        """Tuple of data types carried by the signal."""
        return tuple(
            [param.annotation for param in self._signature.parameters.values()]
        )

    @property
    def info(self) -> str:
        """Signal description."""
        return self._info


class VirtualBus(ABC, Loggable):
    """

    VirtualBus base class.

    The VirtualBus is a mechanism to exchange data between different parts of the system.

    They can be used to emit notifications, as well as carry information to other plugins and/or different RedSun modules.

    VirtualBus' signals are implemented using the `psygnal` library; they can be dynamically registered as class attributes, and accessed as a read-only dictionary.
    """

    _signal_registry: Dict[str, Signal] = {}

    def __init__(self) -> None:
        # pre-register signals added as attributes in the class definition
        self._signal_registry = {
            key: value
            for key, value in type(self).__dict__.items()
            if key.startswith("sig") and isinstance(value, Signal)
        }

    def __setattr__(self, name: str, value: "Any") -> None:
        """
        Overload `__setattr__` to allow registering new signals attributes.

        If the attribute name starts with 'sig' and the value is a `Signal` object, it will be added as instance attribute and added to the signal registry.

        Otherwise, it will be registered as a regular attribute.

        Args:
            name (`str`): attribute name.
            value (`Any`): attribute value.
        """
        if name.startswith("sig") and isinstance(value, Signal):
            if not hasattr(self, name) and name not in self._signal_registry:
                self._signal_registry[name] = value
                super().__setattr__(name, value)
            else:
                self.warning(
                    f"Signal {name} already exists in {self.__class__.__name__}."
                )
        else:
            super().__setattr__(name, value)

    def register_signal(self, name: str, *args: "Any", **kwargs: "Any") -> None:
        r""" 
        
        Create a new `Signal` object with the given name and arguments, and stores it as class attribute.

        >>> channel.registerSignal('sigAcquisitionStarted', str)
        >>> # this will allow to access the signal as an attribute
        >>> channel.sigAcquisitionStarted.connect(mySlot)
        
        Signal names must start with 'sig' prefix.

        Parameters
        ----------
        name : str
            The signal name; this will be used as the attribute name.
        *args : tuple
            Data types carried by the signal.
        **kwargs : dict, optional
            Additional arguments to pass to the `Signal` constructor: \\
            `info` (str): signal description. \\
            Other keyword arguments can be found in the `psygnal.SignalInstance` documentation.
        
        Raises
        ------
        ValueError
            If `name` does not start with 'sig' prefix.
        """
        if not name.startswith("sig"):
            raise ValueError("Signal name must start with 'sig' prefix.")
        else:
            if "info" in kwargs:
                info = kwargs.pop("info")
            else:
                info = "RedSun signal"
            signal = Signal(*args, info=info, **kwargs)
        setattr(self, name, signal)

    @property
    def signals(self) -> "MappingProxyType[str, Signal]":
        """A read-only dictionary with the registered signals."""
        return MappingProxyType(self._signal_registry)
