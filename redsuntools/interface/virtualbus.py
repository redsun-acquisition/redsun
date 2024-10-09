from abc import ABC
from psygnal import SignalInstance
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Dict, TYPE_CHECKING
from redsuntools.log import setup_logger

if TYPE_CHECKING:
    from typing import Any, Tuple

__all__ = ['Signal', 'VirtualBus']

class Signal(SignalInstance):
    """ Small wrapper around `psygnal.SignalInstance` to provide an `info` and a `types` attribute.
    """

    def __init__(self, *argtypes: 'Any', info: str = "RedSun signal", **kwargs) -> None:
        SignalInstance.__init__(self, signature=argtypes, **kwargs)
        self._info = info
    
    @property
    @lru_cache
    def types(self) -> 'Tuple[type, ...]':
        return tuple([param.annotation for param in self._signature.parameters.values()])
    
    @property
    def info(self) -> str:
        return self._info

class VirtualBus(ABC):
    """ VirtualBus base class.

    The VirtualBus is a mechanism to exchange data between different parts of the system. \\
    They can be used to emit notifications, as well as carry information to other plugins and/or different RedSun modules. \\
    VirtualBus' signals are implemented using the `psygnal` library; they can be dynamically registered as class attributes, \\
    and accessed as a read-only dictionary.

    Attributes
    ----------

    signals : MappingProxyType[str, Signal]
        A read-only dictionary with the registered signals.
    """

    _signal_registry: Dict[str, Signal]  = {}

    def __init__(self) -> None:
        # pre-register signals added as attributes in the class definition
        self._signal_registry = {key : value for key, value in type(self).__dict__.items() if key.startswith('sig') and isinstance(value, Signal)}
        self.__logger = setup_logger(self)
    
    def __set__(self, name: str, value: "Any") -> None:
        """
        Overloads `__set__` to allow registering signals attributes.
        
        If the attribute name starts with 'sig' and the value is a `Signal` object, and it is not an existing class attribute,
        it will be added in the signal registry. Otherwise, it will be registered as a 
        regular attribute.

        Parameters
        ----------
        name : str
            The name of the attribute to set.
        value : Any
            The value of the attribute to set.

        """
        if name.startswith('sig') and isinstance(value, Signal):
            if not hasattr(self, name) and not name in self._signal_registry:
                self._signal_registry.update({name: value})
                super().__set__(name, value)
            else:
                self.__logger.warning(f"Signal {name} already exists in {self.__class__.__name__}.")
        else:
            super().__set__(name, value)
    
    def register_signal(self, name: str, *args, **kwargs) -> None:
        """ Creates a new `Signal` object with the given name and arguments,
        and stores it as class attribute.

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
        if not name.startswith('sig'):
            raise ValueError("Signal name must start with 'sig' prefix.")
        else:
            if "info" in kwargs:
                info = kwargs.pop("info")
            else:
                info = "RedSun signal"
            signal = Signal(*args, info=info, **kwargs)
        self.__set__(self, name, signal)
    
    @property
    def signals(self) -> 'MappingProxyType[str, Signal]':
        """ Returns a read-only dictionary with the registered `Signal` objects as attributes.


        Returns
        -------
        MappingProxyType[str, Signal]
            A read-only dictionary with the registered signals

        """
        return MappingProxyType(self._signal_registry)