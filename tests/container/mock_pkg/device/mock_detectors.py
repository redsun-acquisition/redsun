from attrs import define

from redsun.device import Device, SoftAttrR, SoftAttrRW


@define(kw_only=True, slots=False)
class MockDetector(Device):
    """Mock detector device.

    Attributes are :class:`~redsun.device.SoftAttrRW` /
    :class:`~redsun.device.SoftAttrR` instances.  The EGU for ``exposure``
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
            exposure=SoftAttrRW[float](f"{name}-exposure", exposure, units=egu),
            sensor_shape=SoftAttrR[tuple[int, int]](
                f"{name}-sensor_shape",
                tuple(sensor_shape),  # type: ignore[arg-type]
            ),
            pixel_size=SoftAttrR[tuple[float, float, float]](
                f"{name}-pixel_size",
                tuple(pixel_size),  # type: ignore[arg-type]
            ),
            integer=SoftAttrRW[int](f"{name}-integer", integer),
            floating=SoftAttrRW[float](f"{name}-floating", floating),
            string=SoftAttrRW[str](f"{name}-string", string),
        )

    @property
    def parent(self) -> None:
        return None


@define(kw_only=True, slots=False)
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
            exposure=SoftAttrRW[float](f"{name}-exposure", exposure, units=egu),
            sensor_shape=SoftAttrR[tuple[int, int]](
                f"{name}-sensor_shape",
                tuple(sensor_shape),  # type: ignore[arg-type]
            ),
            pixel_size=SoftAttrR[tuple[float, float, float]](
                f"{name}-pixel_size",
                tuple(pixel_size),  # type: ignore[arg-type]
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
