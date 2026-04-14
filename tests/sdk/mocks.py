"""Mock classes for redsun SDK tests."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from typing import Any

from bluesky.plan_stubs import close_run, open_run
from bluesky.run_engine import RunEngine
from bluesky.utils import MsgGenerator

from redsun.device import Device, PDevice, SoftAttrR, SoftAttrRW
from redsun.presenter import PPresenter
from redsun.virtual import IsInjectable, IsProvider, Signal, VirtualContainer


class MockDetector(Device):
    """Mock detector device using soft attributes.

    The EGU for ``exposure`` is embedded in the descriptor document
    (``describe()["<name>-exposure"]["units"]``), not as a separate signal.
    """

    def __init__(
        self,
        name: str,
        *,
        sensor_size: tuple[int, int] = (1024, 1024),
        exposure: float = 1.0,
        exposure_units: str = "ms",
        pixel_size: tuple[int, int, int] = (1, 1, 1),
    ) -> None:
        super().__init__(name)
        self.sensor_size = SoftAttrR[tuple[int, int]](sensor_size)
        self.exposure = SoftAttrRW[float](exposure, units=exposure_units)
        self.pixel_size = SoftAttrR[tuple[int, int, int]](pixel_size)


class MockMotor(Device):
    """Mock motor device with per-axis soft attributes.

    Each axis (x, y, z) is an independent read-write attribute component.
    The EGU is embedded in each axis descriptor (``units`` field) rather
    than exposed as a separate signal.
    """

    def __init__(
        self,
        name: str,
        *,
        units: str = "μm",
    ) -> None:
        super().__init__(name)
        self.x = SoftAttrRW[float](0.0, units=units)
        self.y = SoftAttrRW[float](0.0, units=units)
        self.z = SoftAttrRW[float](0.0, units=units)


class MockDeviceWithChild(Device):
    """Mock device that owns a child :class:`MockMotor`.

    Used to verify that devices hosting sub-device attributes behave
    correctly inside the container and plan-spec machinery.
    """

    def __init__(
        self,
        name: str,
        *,
        units: str = "μm",
    ) -> None:
        super().__init__(name)
        self.stage = MockMotor(name, units=units)
        self.enabled = SoftAttrRW[bool](True)


class MockController(PPresenter, IsProvider, IsInjectable):
    """Mock controller/presenter that optionally provides dependencies."""

    sigBar = Signal()
    sigNewPlan = Signal(object)

    def __init__(
        self,
        name: str,
        devices: Mapping[str, PDevice],
        /,
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.devices = devices
        self.engine = RunEngine({})
        self.plans: list[partial[MsgGenerator[Any]]] = []

        def mock_plan_no_device() -> MsgGenerator[Any]:
            yield from [open_run(), close_run()]

        self.plans.append(partial(mock_plan_no_device))

    def register_providers(self, container: VirtualContainer) -> None: ...

    def inject_dependencies(self, container: VirtualContainer) -> None: ...

    def shutdown(self) -> None: ...


mock_detector = MockDetector("detector", sensor_size=(1024, 1024))
mock_motor = MockMotor("motor", units="μm")
