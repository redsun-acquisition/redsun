from attrs import define, setters

from redsun.device import Device, SoftAttrR, SoftAttrRW


@define(kw_only=True, slots=False, on_setattr=setters.NO_OP)
class MockDetector(Device):
    """Mock detector device.

    Attributes are [`SoftAttrRW`][redsun.device.SoftAttrRW] /
    [`SoftAttrR`][redsun.device.SoftAttrR] instances. The EGU for ``exposure``
    is embedded in its descriptor (``units`` field) rather than exposed as a
    separate signal.
    """

    exposure: SoftAttrRW[float]
    sensor_shape: SoftAttrR[tuple[int, int]]
    pixel_size: SoftAttrR[tuple[float, float, float]]
    integer: SoftAttrRW[int]
    floating: SoftAttrRW[float]
    string: SoftAttrRW[str]

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
        self.__attrs_init__(
            exposure=SoftAttrRW[float](exposure, units=egu),
            sensor_shape=SoftAttrR[tuple[int, int]](
                tuple(sensor_shape),  # type: ignore[arg-type]
            ),
            pixel_size=SoftAttrR[tuple[float, float, float]](
                tuple(pixel_size),  # type: ignore[arg-type]
            ),
            integer=SoftAttrRW[int](integer),
            floating=SoftAttrRW[float](floating),
            string=SoftAttrRW[str](string),
        )


@define(kw_only=True, slots=False, on_setattr=setters.NO_OP)
class MockDetectorWithStorage(MockDetector):
    """Mock detector that declares storage capability via ``storage_info()``."""

    def __init__(self, name: str, /, **kwargs: float | str | tuple) -> None:
        super().__init__(name, **kwargs)


@define(kw_only=True, slots=False)
class NonDerivedDetector:
    """Mock non-derived detector for structural protocol testing."""

    exposure: SoftAttrRW[float]
    sensor_shape: SoftAttrR[tuple[int, int]]
    pixel_size: SoftAttrR[tuple[float, float, float]]
    integer: SoftAttrRW[int]
    floating: SoftAttrRW[float]
    string: SoftAttrRW[str]

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
        self.__attrs_init__(
            exposure=SoftAttrRW[float](exposure, name=f"{name}-exposure", units=egu),
            sensor_shape=SoftAttrR[tuple[int, int]](
                tuple(sensor_shape),  # type: ignore[arg-type]
                name=f"{name}-sensor_shape",
            ),
            pixel_size=SoftAttrR[tuple[float, float, float]](
                tuple(pixel_size),  # type: ignore[arg-type]
                name=f"{name}-pixel_size",
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
