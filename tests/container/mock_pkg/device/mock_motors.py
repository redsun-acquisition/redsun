from typing import Literal

from attrs import define, setters

from redsun.device import Device, SoftAttrR, SoftAttrRW

Axis = Literal["X", "Y", "Z"]


@define(kw_only=True, slots=False, on_setattr=setters.NO_OP)
class MyMotor(Device):
    """Mock motor device.

    Attributes are [`SoftAttrR`][redsun.device.SoftAttrR] /
    [`SoftAttrRW`][redsun.device.SoftAttrRW] instances. The EGU for positions
    is embedded in the ``step_size`` descriptor (``units`` field) rather
    than exposed as a separate signal.
    """

    axis: SoftAttrR[list[Axis]]
    step_size: SoftAttrRW[dict[Axis, float]]
    integer: SoftAttrRW[int]
    floating: SoftAttrRW[float]
    string: SoftAttrRW[str]

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
        self.__attrs_init__(
            axis=SoftAttrR[list[Axis]](_axis),
            step_size=SoftAttrRW[dict[Axis, float]](_step_size, units=egu),
            integer=SoftAttrRW[int](integer),
            floating=SoftAttrRW[float](floating),
            string=SoftAttrRW[str](string),
        )


@define(kw_only=True, slots=False)
class NonDerivedMotor:
    """Mock non-derived motor for structural protocol testing."""

    axis: SoftAttrR[list[Axis]]
    step_size: SoftAttrRW[dict[Axis, float]]
    integer: SoftAttrRW[int]
    floating: SoftAttrRW[float]
    string: SoftAttrRW[str]

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
        self.__attrs_init__(
            axis=SoftAttrR[list[Axis]](_axis, name=f"{name}-axis"),
            step_size=SoftAttrRW[dict[Axis, float]](
                _step_size, name=f"{name}-step_size", units=egu
            ),
            integer=SoftAttrRW[int](integer, name=f"{name}-integer"),
            floating=SoftAttrRW[float](floating, name=f"{name}-floating"),
            string=SoftAttrRW[str](string, name=f"{name}-string"),
        )

    @property
    def parent(self) -> None:
        return None

    @property
    def name(self) -> str:
        return self._name
