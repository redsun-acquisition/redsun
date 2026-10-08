"""The session of the guide "How to write a plan that runs until stopped"."""

from __future__ import annotations

from collections.abc import Iterator, Mapping  # noqa: TC003
from concurrent.futures import Future, wait
from typing import Any, Protocol, runtime_checkable

import bluesky.plan_stubs as bps
from bluesky.protocols import Readable, Triggerable
from bluesky.utils import MsgGenerator  # noqa: TC002
from ophyd_async.core import AsyncStatus, SignalRW, StandardReadable, soft_signal_rw
from psygnal import Signal
from qtpy.QtWidgets import QComboBox, QStackedWidget, QVBoxLayout, QWidget

import redsun.engine.plan_stubs as rps
from redsun import (
    AsDevice,
    AsPresenter,
    AsView,
    DeviceMapping,
    HasPlans,
    Link,
    Placement,
    PlanEntry,
    slot,
)
from redsun.engine import ProgressState, RunEngine
from redsun.engine.actions import ActionManager, ActionState, PlanAction, continuous
from redsun.log import Loggable
from redsun.presenter.plan_spec import (
    PlanSpec,
    UnresolvableAnnotationError,
    collect_arguments,
    create_plan_spec,
    resolve_arguments,
)
from redsun.qt import Dock, QtSession
from redsun.view.qt.utils import ActionButton, PlanWidget, create_plan_widget


class MyCamera(StandardReadable):
    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.frames = soft_signal_rw(int)
        self.shutter = soft_signal_rw(bool)
        super().__init__(name=name)

    @AsyncStatus.wrap
    async def trigger(self) -> None:
        await self.frames.set(await self.frames.get_value() + 1)


# --8<-- [start:protocol]
@runtime_checkable
class Camera(Readable[Any], Triggerable, Protocol):
    shutter: SignalRW[bool]


# --8<-- [end:protocol]
# --8<-- [start:actions]
SNAP = PlanAction(name="snap", description="Take one frame")
SHUTTER = PlanAction(name="shutter", toggle_states=("Open", "Close"))
# --8<-- [end:actions]


# --8<-- [start:controller]
class MyController:
    def __init__(self, name: str) -> None:
        self.name = name
        self.actions = ActionManager()

    # --8<-- [start:live]
    @continuous(pausable=True)
    def live(self, camera: Camera) -> MsgGenerator[None]:
        yield from bps.open_run()
        while True:
            yield from bps.checkpoint()
            yield from bps.trigger_and_read([camera])

    # --8<-- [end:live]
    # --8<-- [start:snapshots]
    @continuous
    def snapshots(
        self, camera: Camera, snap: PlanAction = SNAP, shutter: PlanAction = SHUTTER
    ) -> MsgGenerator[None]:
        yield from bps.open_run()
        while True:
            name = yield from self.actions.wait(snap, shutter)
            try:
                if name == snap.name:
                    yield from bps.trigger_and_read([camera])
                else:
                    yield from bps.mv(camera.shutter, True)
                    yield from self.actions.wait_released(shutter)
            finally:
                if name == shutter.name:
                    yield from bps.mv(camera.shutter, False)
                self.actions.done(name)

    # --8<-- [end:snapshots]
    # --8<-- [start:series]
    def series(
        self, camera: Camera, frames: int = 10, repeats: int = 2
    ) -> MsgGenerator[None]:
        yield from bps.open_run()
        yield from rps.declare_progress("repeats")
        for repeat in range(repeats):
            # --8<-- [start:monitor]
            status = yield from bps.abs_set(
                camera.shutter, True, wait=False, group="shutter"
            )
            yield from rps.monitor_progress("shutter", status, parent="repeats")
            yield from bps.wait(group="shutter")
            # --8<-- [end:monitor]
            yield from rps.declare_progress("series", parent="repeats")
            for frame in range(frames):
                yield from bps.trigger_and_read([camera])
                yield from rps.update_progress(
                    "series", current=frame + 1, initial=0, target=frames, unit="frames"
                )
            yield from rps.update_progress("series", done=True)
            yield from rps.update_progress(
                "repeats", current=repeat + 1, initial=0, target=repeats, unit="repeats"
            )
        yield from rps.update_progress("repeats", done=True)
        yield from bps.close_run()

    # --8<-- [end:series]
    def plan_map(self) -> Mapping[str, PlanEntry]:
        return {
            "live": {"plan": self.live},
            "snapshots": {"plan": self.snapshots},
            "series": {"plan": self.series},
        }


# --8<-- [end:controller]
# --8<-- [start:presenter]
class PlanPresenter(Loggable):
    sig_finished = Signal()
    # --8<-- [start:progress-relay]
    sig_progress = Signal(tuple)
    # --8<-- [end:progress-relay]

    def __init__(self, name: str, *, devices: DeviceMapping) -> None:
        self.name = name
        self.devices = devices
        self.engine = RunEngine()
        self.plans: dict[str, PlanEntry] = {}
        self.specs: dict[str, PlanSpec] = {}
        self.futures: set[Future[Any]] = set()
        # --8<-- [start:progress-connect]
        self.engine.sig_progress.connect(self.sig_progress.emit)
        # --8<-- [end:progress-connect]

    def setup(self, plan_sources: Mapping[str, HasPlans]) -> None:
        for component in plan_sources.values():
            for plan, entry in component.plan_map().items():
                try:
                    self.specs[plan] = create_plan_spec(entry["plan"], self.devices)
                except (UnresolvableAnnotationError, ValueError) as error:
                    self.logger.warning(error)
                    continue
                self.plans[plan] = entry

    # --8<-- [start:presenter-slots]
    @slot
    def run(self, plan: str, values: dict[str, Any]) -> None:
        if self.futures:
            self.logger.warning(f"A plan is running; {plan!r} not started")
            return
        resolved = resolve_arguments(self.specs[plan], values, self.devices)
        args, kwargs = collect_arguments(self.specs[plan], resolved)
        self.watch(self.engine(self.plans[plan]["plan"](*args, **kwargs)))

    @slot
    def toggle(self, plan: str, on: bool, values: dict[str, Any]) -> None:
        if on:
            self.run(plan, values)
        elif self.engine.state != "idle":
            self.watch(self.engine.stop())

    @slot
    def pause(self, paused: bool) -> None:
        if paused:
            self.engine.request_pause(defer=True)
        else:
            self.watch(self.engine.resume())

    def watch(self, future: Future[Any]) -> None:
        self.futures.add(future)
        future.add_done_callback(self.finished)

    def finished(self, future: Future[Any]) -> None:
        self.futures.discard(future)
        if not self.futures and self.engine.state != "paused":
            self.sig_finished.emit()

    def shutdown(self) -> None:
        if self.futures or self.engine.state == "paused":
            wait([self.engine.stop()], timeout=10)

    # --8<-- [end:presenter-slots]


# --8<-- [end:presenter]
# --8<-- [start:view]
class PlanView(QWidget):
    placement: Placement = Dock("right")
    sig_run = Signal(str, dict)
    sig_toggle = Signal(str, bool, dict)
    sig_pause = Signal(bool)
    sig_action_request = Signal(str, bool)

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self.chooser = QComboBox()
        self.pages = QStackedWidget()
        self.chooser.currentIndexChanged.connect(self.pages.setCurrentIndex)
        layout = QVBoxLayout(self)
        layout.addWidget(self.chooser)
        layout.addWidget(self.pages)
        self.widgets: dict[str, PlanWidget] = {}

    def setup(
        self, plan_sources: Mapping[str, HasPlans], devices: DeviceMapping
    ) -> None:
        for component in plan_sources.values():
            for entry in component.plan_map().values():
                try:
                    self.add_plan(create_plan_spec(entry["plan"], devices))
                except (UnresolvableAnnotationError, ValueError):
                    continue

    # --8<-- [start:view-controls]
    def add_plan(self, spec: PlanSpec) -> None:
        widget = create_plan_widget(
            spec,
            run_callback=lambda: self.ask_to_run(spec.name),
            toggle_callback=lambda on: self.ask_to_toggle(spec.name, on),
            pause_callback=lambda paused: self.ask_to_pause(spec.name, paused),
            action_clicked_callback=self.ask,
            action_toggled_callback=self.ask_or_release,
        )
        self.widgets[spec.name] = widget
        self.chooser.addItem(spec.name)
        self.pages.addWidget(widget.group_box)

    def ask_to_run(self, plan: str) -> None:
        self.setEnabled(False)
        self.sig_run.emit(plan, self.widgets[plan].parameters)

    def ask_to_toggle(self, plan: str, on: bool) -> None:
        self.chooser.setEnabled(not on)
        self.widgets[plan].toggle(on)
        self.sig_toggle.emit(plan, on, self.widgets[plan].parameters)

    def ask_to_pause(self, plan: str, paused: bool) -> None:
        self.widgets[plan].pause(paused)
        self.sig_pause.emit(paused)

    @slot
    def on_finished(self) -> None:
        self.setEnabled(True)
        self.chooser.setEnabled(True)
        self.widgets[self.chooser.currentText()].toggle(False)

    # --8<-- [end:view-controls]
    # --8<-- [start:view-actions]
    def ask(self, name: str) -> None:
        self.sig_action_request.emit(name, True)

    def ask_or_release(self, checked: bool, name: str) -> None:
        self.sig_action_request.emit(name, checked)

    @slot
    def on_action_changed(self, name: str, state: str) -> None:
        for widget in self.widgets.values():
            if name in widget.action_buttons:
                self.set_action_button(widget.action_buttons[name], state)

    def set_action_button(self, button: ActionButton, state: str) -> None:
        match state:
            case ActionState.IDLE:
                button.setEnabled(False)
                button.release()
            case ActionState.OFFERED:
                button.setEnabled(True)
            case ActionState.RUNNING:
                button.setEnabled(button.isCheckable())

    # --8<-- [end:view-actions]
    # --8<-- [start:progress-view]
    @slot
    def on_progress(self, scopes: tuple[ProgressState, ...]) -> None:
        self.widgets[self.chooser.currentText()].show_progress(scopes)

    # --8<-- [end:progress-view]


# --8<-- [end:view]
# --8<-- [start:session]
class MyApp(QtSession):
    camera: AsDevice[MyCamera]
    ctrl: AsPresenter[MyController]
    plan_ctrl: AsPresenter[PlanPresenter]
    plan_view: AsView[PlanView]

    def wire(self) -> Iterator[Link]:
        yield self.plan_view.sig_run, self.plan_ctrl.run
        yield self.plan_view.sig_toggle, self.plan_ctrl.toggle
        yield self.plan_view.sig_pause, self.plan_ctrl.pause
        yield self.plan_ctrl.sig_finished, self.plan_view.on_finished
        yield self.plan_view.sig_action_request, self.ctrl.actions.request
        yield self.ctrl.actions.sig_changed, self.plan_view.on_action_changed
        yield self.plan_ctrl.sig_progress, self.plan_view.on_progress


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
