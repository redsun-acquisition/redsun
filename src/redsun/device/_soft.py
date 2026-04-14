"""In-memory (soft) implementations of the device attribute protocols.

These classes provide a concrete, transport-free implementation of
[`AttrR`][redsun.device.AttrR], [`AttrRW`][redsun.device.AttrRW] and
[`AttrT`][redsun.device.AttrT] backed by a plain Python value.  They are
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


class SoftAttr:
    """Base class for all in-memory (soft) device attributes.

    Provides the shared [`name`][] property and [`set_name`][] method
    used by [`SoftAttrR`][redsun.device.SoftAttrR],
    [`SoftAttrRW`][redsun.device.SoftAttrRW], and
    [`SoftAttrT`][redsun.device.SoftAttrT].

    Parameters
    ----------
    name : str
        Fully-qualified attribute name. Injected automatically when
        assigned to an attribute of a [`Device`][redsun.device.Device].
    """

    def __init__(self, *, name: str = "") -> None:
        self._name = name

    @property
    def name(self) -> str:
        """Fully-qualified attribute name."""
        return self._name

    def set_name(self, name: str) -> None:
        """Update the attribute name.

        Called automatically by the parent [`Device`][redsun.device.Device]
        on attribute assignment and when
        [`set_name`][redsun.device.Device.set_name] is called on the parent.
        """
        self._name = name


class SoftAttrR(SoftAttr, Generic[T]):
    """Read-only in-memory device attribute.

    Satisfies [`AttrR`][redsun.device.AttrR] structurally.

    Parameters
    ----------
    initial_value : T
        Starting value. The bluesky ``dtype`` and ``shape`` fields in
        [`describe`][] are inferred from this value's type.
    name : str
        Fully-qualified attribute name, e.g. ``"laser-intensity"``.
        Used as the key in [`read`][] and [`describe`][] dictionaries.
        When assigned to an attribute of a [`Device`][redsun.device.Device],
        the name is injected automatically; passing it explicitly is only
        needed for standalone use.
    units : str, optional
        Optional physical unit string included in the descriptor.
    """

    def __init__(
        self,
        initial_value: T,
        *,
        name: str = "",
        units: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self._value: T = initial_value
        self._units = units
        self._dtype: _DType = _infer_dtype(initial_value)
        self._shape: list[int | None] = _infer_shape(initial_value)
        self._callbacks: list[Callable[[dict[str, Reading[T]]], None]] = []

    def get_value(self) -> T:
        """Return the current value directly."""
        return self._value

    def read(self) -> dict[str, Reading[T]]:
        """Return a bluesky reading keyed by [`name`][]."""
        return {self._name: make_reading(self._value, time.time())}

    def describe(self) -> dict[str, Descriptor]:
        """Return a bluesky descriptor keyed by [`name`][]."""
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

    Extends [`SoftAttrR`][redsun.device.SoftAttrR] with a [`set`][] method.
    Satisfies [`AttrRW`][redsun.device.AttrRW] structurally.

    Parameters
    ----------
    initial_value : T
        Starting value.
    name : str
        Fully-qualified attribute name. Injected automatically when
        assigned to an attribute of a [`Device`][redsun.device.Device].
    units : str, optional
        Optional physical unit string.
    """

    def set(self, value: T) -> Status:
        """Set the attribute value and notify subscribers.

        Parameters
        ----------
        value : T
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


class SoftAttrT(SoftAttr):
    """Trigger in-memory device attribute.

    Satisfies [`AttrT`][redsun.device.AttrT] structurally.

    Parameters
    ----------
    action : Callable[[], None], optional
        Zero-argument callable invoked on each [`trigger`][] call.
        If ``None`` the trigger is a no-op.
    name : str
        Fully-qualified attribute name. Injected automatically when
        assigned to an attribute of a [`Device`][redsun.device.Device].
    """

    def __init__(
        self,
        action: Callable[[], None] | None = None,
        *,
        name: str = "",
    ) -> None:
        super().__init__(name=name)
        self._action: Callable[[], None] = (
            action if action is not None else lambda: None
        )

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
