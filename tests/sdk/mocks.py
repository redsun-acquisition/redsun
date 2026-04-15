"""Mock classes for redsun SDK tests."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from typing import Any

from bluesky.plan_stubs import close_run, open_run
from bluesky.run_engine import RunEngine
from bluesky.utils import MsgGenerator
from ophyd_async.core import Device, SignalRW, StandardReadable, soft_signal_rw

from redsun.presenter import PPresenter
from redsun.virtual import IsInjectable, IsProvider, Signal, VirtualContainer


class MockDetector(StandardReadable):
    """Mock detector device using soft signals.

    The EGU for ``exposure`` is embedded in the descriptor document
    (``describe()["<name>-exposure"]["units"]``), not as a separate signal.
    """

    exposure: SignalRW[float]
    integer: SignalRW[int]
    floating: SignalRW[float]

    def __init__(
        self,
        name: str,
        *,
        exposure: float = 1.0,
        exposure_units: str = "ms",
        integer: int = 0,
        floating: float = 0.0,
        **_: Any,
    ) -> None:
        with self.add_children_as_readables():
            self.exposure = soft_signal_rw(
                float, initial_value=exposure, units=exposure_units
            )
            self.integer = soft_signal_rw(int, initial_value=integer)
            self.floating = soft_signal_rw(float, initial_value=floating)
        super().__init__(name=name)


class MockMotor(StandardReadable):
    """Mock motor device with per-axis soft signals.

    Each axis (x, y, z) is an independent read-write signal component.
    The EGU is embedded in each axis descriptor (``units`` field) rather
    than exposed as a separate signal.
    """

    x: SignalRW[float]
    y: SignalRW[float]
    z: SignalRW[float]

    def __init__(
        self,
        name: str,
        *,
        units: str = "μm",
        **_: Any,
    ) -> None:
        with self.add_children_as_readables():
            self.x = soft_signal_rw(float, initial_value=0.0, units=units)
            self.y = soft_signal_rw(float, initial_value=0.0, units=units)
            self.z = soft_signal_rw(float, initial_value=0.0, units=units)
        super().__init__(name=name)


class MockDeviceWithChild(StandardReadable):
    """Mock device that owns a child [`MockMotor`][tests.sdk.mocks.MockMotor].

    Used to verify that devices hosting sub-device attributes behave
    correctly inside the container and plan-spec machinery.
    """

    stage: MockMotor
    enabled: SignalRW[bool]

    def __init__(
        self,
        name: str,
        *,
        units: str = "μm",
    ) -> None:
        self.stage = MockMotor(name, units=units)
        with self.add_children_as_readables():
            self.enabled = soft_signal_rw(bool, initial_value=True)
        super().__init__(name=name)


class MockController(PPresenter, IsProvider, IsInjectable):
    """Mock controller/presenter that optionally provides dependencies."""

    sigBar = Signal()
    sigNewPlan = Signal(object)

    def __init__(
        self,
        name: str,
        devices: Mapping[str, Device],
        /,
        **_: Any,
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


mock_detector = MockDetector("detector")
mock_motor = MockMotor("motor", units="μm")
