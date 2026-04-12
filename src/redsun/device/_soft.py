"""In-memory (soft) implementations of the device attribute protocols.

These classes provide a concrete, transport-free implementation of
:class:`~redsun.device.AttrR`, :class:`~redsun.device.AttrRW` and
:class:`~redsun.device.AttrT` backed by a plain Python value.  They are
intended for:

- Test fixtures and simulation devices that do not talk to real hardware.
- Default attribute implementations in device subclasses where the value
  is managed entirely in software.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable, Generic, Literal, TypeVar

from redsun.engine import Status
from redsun.utils.descriptors import make_reading

if TYPE_CHECKING:
    from bluesky.protocols import Descriptor, Reading

T = TypeVar("T")

_DTYPE_MAP: dict[type, _DType] = {
    bool: "boolean",
    int: "integer",
    float: "number",
    str: "string",
}


def _infer_dtype(value: Any) -> _DType:
    """Infer a bluesky dtype string from a Python value."""
    # bool must be checked before int because bool is a subclass of int.
    for py_type, dtype in _DTYPE_MAP.items():
        if type(value) is py_type:
            return dtype
    if isinstance(value, (list, tuple)):
        return "array"
    return "string"


_DType = Literal["boolean", "integer", "number", "string", "array"]


def _infer_shape(value: Any) -> list[int | None]:
    if isinstance(value, (list, tuple)):
        return [len(value)]
    return []


class SoftAttrR(Generic[T]):
    """Read-only in-memory device attribute.

    Satisfies :class:`~redsun.device.AttrR` structurally.

    Parameters
    ----------
    name:
        Fully-qualified attribute name, e.g. ``"laser-intensity"``.
        This string is used as the key in :meth:`read` and
        :meth:`describe` dictionaries.
    initial_value:
        Starting value.  The bluesky ``dtype`` and ``shape`` fields in
        :meth:`describe` are inferred from this value's type.
    units:
        Optional physical unit string included in the descriptor.
    """

    def __init__(
        self,
        name: str,
        initial_value: T,
        *,
        units: str | None = None,
    ) -> None:
        self._name = name
        self._value: T = initial_value
        self._units = units
        self._dtype: _DType = _infer_dtype(initial_value)
        self._shape: list[int | None] = _infer_shape(initial_value)
        self._callbacks: list[Callable[[dict[str, Reading[T]]], None]] = []

    @property
    def name(self) -> str:
        """Fully-qualified attribute name."""
        return self._name

    def get_value(self) -> T:
        """Return the current value directly."""
        return self._value

    def read(self) -> dict[str, Reading[T]]:
        """Return a bluesky reading keyed by :attr:`name`."""
        return {self._name: make_reading(self._value, time.time())}

    def describe(self) -> dict[str, Descriptor]:
        """Return a bluesky descriptor keyed by :attr:`name`."""
        d: Descriptor = {
            "source": f"soft://{self._name}",
            "dtype": self._dtype,
            "shape": self._shape,
        }
        if self._units is not None:
            d["units"] = self._units
        return {self._name: d}

    def subscribe(self, function: Callable[[dict[str, Reading[T]]], None]) -> None:
        """Register *function* and call it immediately with the current reading."""
        self._callbacks.append(function)
        function(self.read())

    def clear_sub(self, function: Callable[[dict[str, Reading[T]]], None]) -> None:
        """Deregister a previously registered callback."""
        self._callbacks.remove(function)

    def _notify(self) -> None:
        reading = self.read()
        for cb in self._callbacks:
            cb(reading)


class SoftAttrRW(SoftAttrR[T]):
    """Read-write in-memory device attribute.

    Extends :class:`SoftAttrR` with a :meth:`set` method.
    Satisfies :class:`~redsun.device.AttrRW` structurally.

    Parameters
    ----------
    name:
        Fully-qualified attribute name.
    initial_value:
        Starting value.
    units:
        Optional physical unit string.
    """

    def set(self, value: T) -> Status:
        """Set the attribute value and notify subscribers.

        Parameters
        ----------
        value:
            New value to store.

        Returns
        -------
        Status
            A status object that is already marked finished when returned.
        """
        s = Status()
        self._value = value
        self._notify()
        s.set_finished()
        return s


class SoftAttrT:
    """Trigger in-memory device attribute.

    Satisfies :class:`~redsun.device.AttrT` structurally.

    Parameters
    ----------
    name:
        Fully-qualified attribute name.
    action:
        Zero-argument callable invoked on each :meth:`trigger` call.
        If ``None`` the trigger is a no-op.
    """

    def __init__(
        self,
        name: str,
        action: Callable[[], None] | None = None,
    ) -> None:
        self._name = name
        self._action: Callable[[], None] = (
            action if action is not None else lambda: None
        )

    @property
    def name(self) -> str:
        """Fully-qualified attribute name."""
        return self._name

    def trigger(self) -> Status:
        """Execute the action and return a completed status.

        Returns
        -------
        Status
            A status object that is already marked finished when returned.
        """
        s = Status()
        self._action()
        s.set_finished()
        return s
