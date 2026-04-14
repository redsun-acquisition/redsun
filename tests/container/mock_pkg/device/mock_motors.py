from __future__ import annotations

from typing import Literal

from redsun.device import Device, SoftAttrR, SoftAttrRW

Axis = Literal["X", "Y", "Z"]


class MyMotor(Device):
    """Mock motor device.

    Attributes are [`SoftAttrR`][redsun.device.SoftAttrR] /
    [`SoftAttrRW`][redsun.device.SoftAttrRW] instances. The EGU for positions
    is embedded in the ``step_size`` descriptor (``units`` field) rather
    than exposed as a separate signal.
    """

    def __init__(
        self,
        name: str,
        /,
        *,
        axis: list[Axis] | None = None,
        step_size: dict[Axis, float] | None = None,
        egu: str = "mm",
        integer: int = 0,
        floating: float = 0.0,
        string: str = "",
    ) -> None:
        super().__init__(name)
        _axis: list[Axis] = axis or ["X"]
        _step_size: dict[Axis, float] = step_size or {ax: 0.1 for ax in _axis}
        self.axis = SoftAttrR[list[Axis]](_axis)
        self.step_size = SoftAttrRW[dict[Axis, float]](_step_size, units=egu)
        self.integer = SoftAttrRW[int](integer)
        self.floating = SoftAttrRW[float](floating)
        self.string = SoftAttrRW[str](string)


class NonDerivedMotor:
    """Mock non-derived motor for structural protocol testing."""

    def __init__(
        self,
        name: str,
        /,
        *,
        axis: list[Axis] | None = None,
        step_size: dict[Axis, float] | None = None,
        egu: str = "mm",
        integer: int = 0,
        floating: float = 0.0,
        string: str = "",
    ) -> None:
        self._name = name
        _axis: list[Axis] = axis or ["X"]
        _step_size: dict[Axis, float] = step_size or {ax: 0.1 for ax in _axis}
        self.axis = SoftAttrR[list[Axis]](_axis, name=f"{name}-axis")
        self.step_size = SoftAttrRW[dict[Axis, float]](
            _step_size, name=f"{name}-step_size", units=egu
        )
        self.integer = SoftAttrRW[int](integer, name=f"{name}-integer")
        self.floating = SoftAttrRW[float](floating, name=f"{name}-floating")
        self.string = SoftAttrRW[str](string, name=f"{name}-string")

    @property
    def parent(self) -> None:
        return None

    @property
    def name(self) -> str:
        return self._name
