from __future__ import annotations

from redsun.device import Device, SoftAttrR, SoftAttrRW


class MockDetector(Device):
    """Mock detector device.

    Attributes are [`SoftAttrRW`][redsun.device.SoftAttrRW] /
    [`SoftAttrR`][redsun.device.SoftAttrR] instances. The EGU for ``exposure``
    is embedded in its descriptor (``units`` field) rather than exposed as a
    separate signal.
    """

    def __init__(
        self,
        name: str,
        /,
        *,
        exposure: float = 1.0,
        egu: str = "s",
        sensor_shape: tuple[int, int] = (1, 1),
        pixel_size: tuple[float, float, float] = (1.0, 1.0, 1.0),
        integer: int = 0,
        floating: float = 0.0,
        string: str = "",
    ) -> None:
        super().__init__(name)
        self.exposure = SoftAttrRW[float](exposure, units=egu)
        self.sensor_shape = SoftAttrR[tuple[int, int]](
            tuple(sensor_shape),  # type: ignore[arg-type]
        )
        self.pixel_size = SoftAttrR[tuple[float, float, float]](
            tuple(pixel_size),  # type: ignore[arg-type]
        )
        self.integer = SoftAttrRW[int](integer)
        self.floating = SoftAttrRW[float](floating)
        self.string = SoftAttrRW[str](string)


class MockDetectorWithStorage(MockDetector):
    """Mock detector that declares storage capability via ``storage_info()``."""

    def __init__(self, name: str, /, **kwargs: float | str | tuple) -> None:
        super().__init__(name, **kwargs)


class NonDerivedDetector:
    """Mock non-derived detector for structural protocol testing.

    Not a [`Device`][redsun.device.Device] subclass — used to verify that
    structural protocols are satisfied purely by duck typing.
    """

    def __init__(
        self,
        name: str,
        /,
        *,
        exposure: float = 1.0,
        egu: str = "s",
        sensor_shape: tuple[int, int] = (1, 1),
        pixel_size: tuple[float, float, float] = (1.0, 1.0, 1.0),
        integer: int = 0,
        floating: float = 0.0,
        string: str = "",
    ) -> None:
        self._name = name
        self.exposure = SoftAttrRW[float](exposure, name=f"{name}-exposure", units=egu)
        self.sensor_shape = SoftAttrR[tuple[int, int]](
            tuple(sensor_shape),  # type: ignore[arg-type]
            name=f"{name}-sensor_shape",
        )
        self.pixel_size = SoftAttrR[tuple[float, float, float]](
            tuple(pixel_size),  # type: ignore[arg-type]
            name=f"{name}-pixel_size",
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
