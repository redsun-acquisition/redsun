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
    """Mock detector device using soft attributes."""

    def __init__(
        self,
        name: str,
        *,
        sensor_size: tuple[int, int] = (1024, 1024),
        exposure_egu: str = "ms",
        pixel_size: tuple[int, int, int] = (1, 1, 1),
    ) -> None:
        super().__init__(name)
        self.sensor_size = SoftAttrR[tuple[int, int]](
            f"{name}-sensor_size", sensor_size
        )
        self.exposure_egu = SoftAttrR(f"{name}-exposure_egu", exposure_egu)
        self.pixel_size = SoftAttrR[tuple[int, int, int]](
            f"{name}-pixel_size", pixel_size
        )


class MockMotor(Device):
    """Mock motor device with per-axis soft attributes.

    Each axis (x, y, z) is an independent read-write attribute component,
    reflecting the design principle that axes are first-class signal objects
    rather than items in a list.
    """

    def __init__(
        self,
        name: str,
        *,
        step_egu: str = "μm",
    ) -> None:
        super().__init__(name)
        self.step_egu: SoftAttrR = SoftAttrR[str](f"{name}-step_egu", step_egu)
        self.x = SoftAttrRW[float](f"{name}-x", 0.0, units=step_egu)
        self.y = SoftAttrRW[float](f"{name}-y", 0.0, units=step_egu)
        self.z = SoftAttrRW[float](f"{name}-z", 0.0, units=step_egu)


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
mock_motor = MockMotor("motor", step_egu="μm")
