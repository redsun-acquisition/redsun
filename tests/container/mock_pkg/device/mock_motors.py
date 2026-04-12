from typing import Literal

from attrs import define

from redsun.device import Device, SoftAttrR, SoftAttrRW

Axis = Literal["X", "Y", "Z"]


@define(kw_only=True, slots=False)
class MyMotor(Device):
    """Mock motor device.

    Attributes are :class:`~redsun.device.SoftAttrR` /
    :class:`~redsun.device.SoftAttrRW` instances.  The EGU for positions
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
            axis=SoftAttrR[list[Axis]](f"{name}-axis", _axis),
            step_size=SoftAttrRW[dict[Axis, float]](
                f"{name}-step_size", _step_size, units=egu
            ),
            integer=SoftAttrRW[int](f"{name}-integer", integer),
            floating=SoftAttrRW[float](f"{name}-floating", floating),
            string=SoftAttrRW[str](f"{name}-string", string),
        )

    @property
    def parent(self) -> None:
        return None


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
            axis=SoftAttrR[list[Axis]](f"{name}-axis", _axis),
            step_size=SoftAttrRW[dict[Axis, float]](
                f"{name}-step_size", _step_size, units=egu
            ),
            integer=SoftAttrRW[int](f"{name}-integer", integer),
            floating=SoftAttrRW[float](f"{name}-floating", floating),
            string=SoftAttrRW[str](f"{name}-string", string),
        )

    @property
    def parent(self) -> None:
        return None

    @property
    def name(self) -> str:
        return self._name
