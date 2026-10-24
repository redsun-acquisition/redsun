"""A session declaring root devices, and what it offers of their trees."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from functools import cached_property
from typing import TYPE_CHECKING, Annotated

import bluesky.plan_stubs as bps
import pytest
from bluesky.utils import MsgGenerator
from ophyd_async.core import (
    Device,
    DeviceConnector,
    DeviceMap,
    DeviceVector,
    MovableLogic,
    NotConnectedError,
    SignalRW,
    StandardMovable,
    soft_command,
    soft_signal_rw,
)
from ophyd_async.epics.core import EpicsDevice, PvSuffix
from qtpy import QtWidgets

from redsun import (
    Alias,
    AsDevice,
    AsPresenter,
    AsView,
    Declare,
    DeviceMapping,
    DevicesOf,
    Link,
    Session,
    links_between,
)
from redsun.aio import run_coro
from redsun.engine.plan_stubs import lock_wrapper
from redsun.errors import BuildError
from redsun.presenter import (
    AcquisitionPresenter,
    LightPresenter,
    PositionerPresenter,
)
from redsun.qt import QtSession
from redsun.utils.devices import Axis, Light
from redsun.view.qt.builtins import (
    AcquisitionView,
    LightGroup,
    LightView,
    PositionerGroup,
    PositionerView,
)
from tests.sdk.mocks import SoftAxis, SoftLight, XYStage
from tests.sdk.view.helpers import child

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from redsun import PlanEntry
    from redsun.testing import BuildSession


def do_nothing() -> None:
    """Stand in for the work a command does."""


class Scope(Device):
    """A root holding a stage, an axis, a map of lights and a command."""

    def __init__(
        self, name: str = "", connector: DeviceConnector | None = None
    ) -> None:
        self.xy = XYStage("")
        self.focus = SoftAxis()
        self.lights = DeviceMap({"laser": SoftLight()})
        self.home = soft_command(do_nothing)
        super().__init__(name=name, connector=connector)


class Leaf(Device):
    """A device holding one signal."""

    def __init__(self, name: str = "") -> None:
        self.power = soft_signal_rw(float)
        super().__init__(name=name)


class Holder(Device):
    """A device holding the leaves `x` and `blue`."""

    def __init__(self, name: str = "") -> None:
        self.x = Leaf()
        self.blue = Leaf()
        super().__init__(name=name)


class Lamp(Device):
    """A root whose map entry `led-blue` takes the name of the child `blue` of `led`."""

    def __init__(self, name: str = "") -> None:
        self.bank = DeviceMap({"led-blue": Leaf(), "led": Holder()})
        super().__init__(name=name)


class LateEntry(Device):
    """A root that adds a map entry after it was named."""

    def __init__(self, name: str = "") -> None:
        self.bank = DeviceMap({"first": Leaf()})
        super().__init__(name=name)
        self.bank["late"] = Leaf()


class Growing(Device):
    """A root whose connector adds an axis while connecting."""

    def __init__(
        self, name: str = "", connector: DeviceConnector | None = None
    ) -> None:
        self.extra = DeviceVector[SoftAxis]({})
        super().__init__(name=name, connector=connector)


class AddsAnAxis(DeviceConnector):
    """Connector that adds an axis to a `Growing` device, then names it."""

    async def connect_real(
        self, device: Device, timeout: float, force_reconnect: bool
    ) -> None:
        assert isinstance(device, Growing)
        device.extra[1] = SoftAxis()
        device.set_name(device.name)
        await super().connect_real(device, timeout, force_reconnect)


class Refusing(DeviceConnector):
    """Connector of a device nothing answers for."""

    async def connect_real(
        self, device: Device, timeout: float, force_reconnect: bool
    ) -> None:
        raise NotConnectedError("no answer")


class EpicsAxis(EpicsDevice, StandardMovable[float]):
    """An axis reached over EPICS, its position declared with an annotation."""

    position: Annotated[SignalRW[float], PvSuffix("Position")]

    @cached_property
    def movable_logic(self) -> MovableLogic[float]:
        """Setpoint and readback of the axis, which are one signal."""
        return MovableLogic(setpoint=self.position, readback=self.position)


class EpicsStage(EpicsDevice):
    """A stage whose axes `x` and `y` are declared with annotations."""

    x: Annotated[EpicsAxis, PvSuffix("X:")]
    y: Annotated[EpicsAxis, PvSuffix("Y:")]


class EpicsScope(EpicsDevice):
    """A root whose stage and focus axis are declared with annotations."""

    xy: Annotated[EpicsStage, PvSuffix("XY:")]
    focus: Annotated[EpicsAxis, PvSuffix("FOCUS:")]


class Recorder:
    """Presenter keeping what the session answered about devices."""

    def __init__(
        self,
        name: str,
        *,
        devices: DeviceMapping,
        axes: DevicesOf[Axis],
        lights: DevicesOf[Light],
    ) -> None:
        self.name = name
        self.devices = devices
        self.axes = axes
        self.lights = lights


class HoldingPlans:
    """Offers one plan, which holds its motor until `gate` is set."""

    def __init__(self, name: str, gate: threading.Event) -> None:
        self.name = name
        self.gate = gate

    def plan_map(self) -> Mapping[str, PlanEntry]:
        """Return the plans by name."""
        return {"hold": {"plan": self.hold}}

    def hold(self, motor: SoftAxis) -> MsgGenerator[None]:
        """Move *motor* to 1, then wait for the gate, holding *motor* all along."""
        yield from lock_wrapper(self.move_and_wait(motor), motor)

    def move_and_wait(self, motor: SoftAxis) -> MsgGenerator[None]:
        """Move *motor* to 1, then wait for the gate."""
        yield from bps.mv(motor, 1.0)
        yield from bps.wait_for([lambda: asyncio.to_thread(self.gate.wait)])


class ScopeApp(Session):
    scope: AsDevice[Scope]
    recorder: AsPresenter[Recorder]


class StackedApp(QtSession):
    scope: AsDevice[Scope]
    plans: AsPresenter[HoldingPlans]
    acquisition: AsPresenter[AcquisitionPresenter]
    positioner: AsPresenter[PositionerPresenter]
    lights: AsPresenter[LightPresenter]
    acquisition_view: AsView[AcquisitionView]
    positioner_view: AsView[PositionerView]
    lights_view: AsView[LightView]

    def wire(self) -> Iterator[Link]:
        """Link each view to its presenter, and the plan locks to all of them."""
        yield from links_between(self.acquisition_view, self.acquisition)
        yield from links_between(self.positioner_view, self.positioner)
        yield from links_between(self.lights_view, self.lights)
        yield from links_between(self.acquisition, self.positioner)
        yield from links_between(self.acquisition, self.positioner_view)
        yield from links_between(self.acquisition, self.lights)
        yield from links_between(self.acquisition, self.lights_view)


class EpicsScopeApp(Session):
    scope: Annotated[AsDevice[EpicsScope], Declare(prefix="SCOPE:")]
    recorder: AsPresenter[Recorder]
    positioner: AsPresenter[PositionerPresenter]


class AcrossTrees(Session):
    stage: AsDevice[Holder]
    stage_x: Annotated[AsDevice[Leaf], Alias("stage-x")]


class InsideOneTree(Session):
    lamp: AsDevice[Lamp]


class LateEntryApp(Session):
    late: AsDevice[LateEntry]


class GrowingApp(Session):
    growing: Annotated[AsDevice[Growing], Declare(connector=AddsAnAxis())]
    recorder: AsPresenter[Recorder]


class UnpluggedApp(Session):
    scope: Annotated[AsDevice[Scope], Declare(connector=Refusing())]
    stage: AsDevice[Holder]
    recorder: AsPresenter[Recorder]


def test_a_root_and_every_device_below_it_are_indexed(build: BuildSession) -> None:
    """Hold every device of the tree in `DeviceMapping` by name, signals and commands left out."""
    app = build(ScopeApp)

    assert set(app.recorder.devices) == {
        "scope",
        "scope-xy",
        "scope-xy-x",
        "scope-xy-y",
        "scope-focus",
        "scope-lights",
        "scope-lights-laser",
    }
    assert app.recorder.devices["scope-xy-x"] is app.scope.xy.x


def test_devices_of_answers_with_every_matching_device_in_the_tree(
    build: BuildSession,
) -> None:
    """Answer `DevicesOf` with each device that satisfies the protocol, wherever it sits."""
    app = build(ScopeApp)

    assert set(app.recorder.axes) == {"scope-xy-x", "scope-xy-y", "scope-focus"}
    assert set(app.recorder.lights) == {"scope-lights-laser"}


def test_children_declared_with_annotations_join_the_tree(build: BuildSession) -> None:
    """Index and box the devices an `EpicsDevice` declares with annotations."""
    app = build(EpicsScopeApp, {"mock": True})

    assert set(app.recorder.devices) == {
        "scope",
        "scope-xy",
        "scope-xy-x",
        "scope-xy-y",
        "scope-focus",
    }
    assert {box: set(rows) for box, rows in app.positioner.axes.items()} == {
        "scope": {"focus"},
        "scope-xy": {"x", "y"},
    }
    path = app.positioner.axes["scope-xy"]["x"].path
    assert path is not None
    assert str(path.parent) == "scope / xy"


@pytest.mark.parametrize("app", [AcrossTrees, InsideOneTree])
def test_two_devices_with_one_name_are_refused(
    build: BuildSession, app: type[Session]
) -> None:
    """Stop the build when two devices of the index share a name, naming both."""
    with pytest.raises(BuildError, match=r"stage-x|lamp-bank-led-blue") as raised:
        build(app)

    assert str(raised.value).count(" and ") == 1


def test_a_device_with_no_name_is_refused(build: BuildSession) -> None:
    """Stop the build when a container entry was left without a name."""
    with pytest.raises(BuildError, match="bank.late"):
        build(LateEntryApp)


def test_a_child_made_while_connecting_is_indexed(build: BuildSession) -> None:
    """Index a child a device adds during connect."""
    app = build(GrowingApp)

    assert "growing-extra-1" in app.recorder.axes


def test_a_root_that_fails_to_connect_leaves_its_tree_out(build: BuildSession) -> None:
    """Leave out of the index every device of a root that did not connect."""
    app = build(UnpluggedApp)

    assert set(app.recorder.devices) == {"stage", "stage-x", "stage-blue"}


def test_session_devices_still_lists_the_declared_devices(build: BuildSession) -> None:
    """Keep `Session.devices` to the devices the session declared."""
    app = build(ScopeApp)

    assert set(app.devices) == {"scope"}


@pytest.mark.qt
def test_a_session_runs_on_one_root_device(
    qapp: QtWidgets.QApplication,
    build: BuildSession,
    wait_until: Callable[..., bool],
    tmp_path: Path,
) -> None:
    """Run the built-in stacks on one root: lights, boxes, plan arguments and locks."""
    gate = threading.Event()
    app = build(
        StackedApp,
        {
            "storage": {"base_dir": str(tmp_path)},
            "presenters": {"plans": {"gate": gate}},
        },
    )
    lights = [g.title() for g in app.lights_view.findChildren(LightGroup)]
    boxes = {g.title(): g for g in app.positioner_view.findChildren(PositionerGroup)}
    xy = child(boxes["scope / xy"], QtWidgets.QAbstractButton, "save")
    focus = child(boxes["scope"], QtWidgets.QAbstractButton, "save")
    motor = app.acquisition.plans["hold"].parameters[0]

    app.acquisition_view.sig_launch.emit("hold", {"motor": "scope-xy-x"}, ())
    assert wait_until(lambda: not xy.isEnabled())
    held = focus.isEnabled()
    run_coro(app.positioner.move("scope-xy", "x", 5.0))
    run_coro(app.positioner.move("scope-xy", "y", 1.0))
    gate.set()
    assert wait_until(xy.isEnabled)

    assert lights == ["scope / lights.laser"]
    assert set(boxes) == {"scope / xy", "scope"}
    assert motor.labels["scope-xy-x"] == "scope / xy.x"
    assert held
    assert run_coro(app.scope.xy.x.locate())["readback"] == 1.0
    assert run_coro(app.scope.xy.y.locate())["readback"] == 1.0
