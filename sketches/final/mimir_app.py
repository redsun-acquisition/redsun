# ruff: noqa
"""What a bundle author writes, end to end.

Three real components from redsun-mimir, rewritten, then the container that
declares them. Compare against the originals in redsun-mimir:
`presenter/motor.py`, `view/motor.py`, `presenter/acquisition.py`,
`configurations/_full_simulation.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated as A, Any

from bluesky.run_engine import RunEngine
from redsun.containers import (
    AppContainer,
    Declare,
    DocumentCallbacks,
    FromConfig,
    Qt,
    provides,
)
from redsun.log import Loggable
from redsun.presenter import Presenter
from redsun.storage import SessionPathProvider
from redsun.view.qt import QtView
from redsun.virtual import Signal, VirtualContainer, slot

from .mimir_providers import MotorDescription, MotorReadbacks, MotorReadings

if TYPE_CHECKING:
    from collections.abc import Mapping

    from bluesky.protocols import Reading
    from ophyd_async.core import DeviceMap


class MotorPresenter(Presenter, Loggable):
    """Unchanged except that `devices` is asked for rather than mandated.

    `register_providers` is gone. The three snapshots it used to bind are the
    three methods it used to call, now marked `@provides`. There is no
    container parameter, no build stage to know, and no separate provider
    module: the presenter carries its own.
    """

    sig_moved = Signal(str, str, float)

    def __init__(
        self,
        name: str,
        /,
        devices: DeviceMap,
        timeout: float = 2.0,
    ) -> None:
        super().__init__(name)
        self.devices = devices
        self.timeout = timeout

    @provides
    def devices_readings(self) -> MotorReadings: ...

    @provides
    def devices_description(self) -> MotorDescription: ...

    @provides
    def devices_readbacks(self) -> MotorReadbacks: ...

    @slot
    def move(self, motor: str, axis: str, displacement: float) -> None: ...


class MotorView(QtView, Loggable):
    """`register_providers` and `inject_dependencies` are both gone.

    What they did is now visible in the signature. The comment the original
    carried, that the subscription must happen after the labels exist, stops
    being a caveat: `setup_ui` runs two statements earlier.
    """

    sig_motor_move = Signal(str, str, float)

    def __init__(
        self,
        name: str,
        /,
        bus: VirtualContainer,
        readings: MotorReadings,
        description: MotorDescription,
        readbacks: MotorReadbacks,
        step_size: float = 10.0,
    ) -> None:
        super().__init__(name)
        self.step_size = step_size
        self.setup_ui(readings, description)
        for readback in readbacks.values():
            bus.subscribe(readback, self.update_setpoint)

    def setup_ui(
        self, readings: MotorReadings, description: MotorDescription
    ) -> None: ...

    @slot
    def update_setpoint(self, reading: Mapping[str, Reading[Any]]) -> None: ...


class AcquisitionPresenter(Presenter, Loggable):
    """Built in the WIRED stage, because of what it asks for.

    `DocumentCallbacks` is provided at `AppScope.WIRED`, so this presenter is
    resolved after every other component exists and the registry is populated.
    Nothing in the declaration says so, and there is no lifecycle hook.
    """

    def __init__(
        self,
        name: str,
        /,
        devices: DeviceMap,
        callbacks: DocumentCallbacks,
        expected: frozenset[str] | None = None,
    ) -> None:
        super().__init__(name)
        self.models = devices
        self.engine = RunEngine()
        self.callback_tokens = {
            cb_name: self.engine.subscribe(callback)
            for cb_name, callback in callbacks.items()
            if expected is None or cb_name in expected
        }
        if not self.callback_tokens:
            self.logger.warning(
                "No document callbacks subscribed: live visualization and "
                "median filtering will produce nothing."
            )


class StorageView(QtView):
    """An optional collaborator: nothing may provide it in a given session."""

    def __init__(
        self,
        name: str,
        /,
        bus: VirtualContainer,
        paths: SessionPathProvider | None = None,
    ) -> None:
        super().__init__(name)
        if paths is None:
            self._placeholder()
            return
        bus.subscribe(paths.signals.base_dir, self.update_base_dir)

    def _placeholder(self) -> None: ...

    @slot
    def update_base_dir(self, reading: Mapping[str, Reading[str]]) -> None: ...


class MimirSimulator(AppContainer[Qt]):
    """The example container, against `full_configuration.yaml` unchanged.

    Every keyword argument still comes from the file: the attribute name is
    the configuration key, so `timeout: 2.0` under `presenters.motor_ctrl`
    reaches `MotorPresenter.timeout` with nothing said here. `FromConfig`
    appears three times only because those YAML keys are not identifiers.
    """

    config = Path(__file__).parent / "full_configuration.yaml"

    mmcamera: A[MMDemoCamera, FromConfig("camera1")]
    XY: A[MMDemoXYStage, FromConfig("xy-motor")]
    Z: A[MMDemoZStage, FromConfig("z-motor")]
    laser: MockLightDevice
    led: MockLightDevice

    storage_ctrl: StoragePresenter
    median_ctrl: MedianPresenter
    det_ctrl: DetectorPresenter
    acq_ctrl: AcquisitionPresenter
    light_ctrl: LightPresenter
    motor_ctrl: MotorPresenter

    acq_widget: AcquisitionView
    img_widget: ImageView
    det_widget: DetectorView
    light_widget: LightView
    motor_widget: A[MotorView, Declare(step_size=5.0)]
    storage_widget: StorageView

    def wire(self) -> None:
        wire_detector(self, self.det_ctrl, self.det_widget, self.img_widget)
        wire_median(self, self.median_ctrl, self.img_widget)
        wire_motor(self, self.motor_ctrl, self.motor_widget)
        wire_light(self, self.light_ctrl, self.light_widget)
        wire_acquisition(
            self,
            self.acq_ctrl,
            self.acq_widget,
            storage=self.storage_ctrl,
            median=self.median_ctrl,
        )


def run() -> None:
    app = MimirSimulator().build()
    app.connect_devices()
