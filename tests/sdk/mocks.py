"""Mock classes for redsun SDK tests."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from typing import Any

from bluesky.plan_stubs import close_run, open_run
from bluesky.protocols import Descriptor, Reading
from bluesky.run_engine import RunEngine
from bluesky.utils import MsgGenerator

from redsun.device import Device, PDevice
from redsun.presenter import PPresenter
from redsun.virtual import IsProvider, Signal, VirtualContainer


class MockDetector(Device):
    """Mock detector device."""

    def __init__(
        self,
        name: str,
        *,
        sensor_size: tuple[int, int] = (1024, 1024),
        exposure_egu: str = "ms",
        pixel_size: tuple[int, int, int] = (1, 1, 1),
    ) -> None:
        super().__init__(name)
        self.sensor_size = sensor_size
        self.exposure_egu = exposure_egu
        self.pixel_size = pixel_size

    def describe_configuration(self) -> dict[str, Descriptor]:
        return {
            "sensor_size": {
                "source": f"{self.name}.sensor_size",
                "dtype": "array",
                "shape": [2],
            }
        }

    def read_configuration(self) -> dict[str, Reading[Any]]:
        return {
            "sensor_size": {
                "value": self.sensor_size,
                "timestamp": 0.0,
            }
        }


class MockMotor(Device):
    """Mock motor device."""

    def __init__(
        self,
        name: str,
        *,
        step_egu: str = "\u03bcm",
        axes: list[str] | None = None,
    ) -> None:
        super().__init__(name)
        self.step_egu = step_egu
        self.axes = axes or ["X"]

    def describe_configuration(self) -> dict[str, Descriptor]:
        return {
            "step_egu": {
                "source": f"{self.name}.step_egu",
                "dtype": "string",
                "shape": [],
            }
        }

    def read_configuration(self) -> dict[str, Reading[Any]]:
        return {
            "step_egu": {
                "value": self.step_egu,
                "timestamp": 0.0,
            }
        }


class MockController(PPresenter, IsProvider):
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
mock_motor = MockMotor("motor", step_egu="\u03bcm", axes=["X", "Y", "Z"])
