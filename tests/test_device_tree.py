"""A session declaring root devices, and what it offers of their trees."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Protocol

import pytest
from ophyd_async.core import (
    Device,
    DeviceConnector,
    DeviceMap,
    DeviceVector,
    NotConnectedError,
    soft_command,
    soft_signal_rw,
)

from redsun import (
    Alias,
    AsDevice,
    AsPresenter,
    Declare,
    DeviceMapping,
    DevicesOf,
    Session,
)
from redsun.errors import BuildError
from redsun.utils.devices import Light
from tests.sdk.mocks import SoftAxis, SoftLight, XYStage

if TYPE_CHECKING:
    from bluesky.protocols import Location

    from redsun.testing import BuildSession


def do_nothing() -> None:
    """Stand in for the work a command does."""


class Locating(Protocol):
    """A device that reports where it is."""

    async def locate(self) -> Location[float]: ...


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


class Recorder:
    """Presenter keeping what the session answered about devices."""

    def __init__(
        self,
        name: str,
        *,
        devices: DeviceMapping,
        axes: DevicesOf[Locating],
        lights: DevicesOf[Light],
    ) -> None:
        self.name = name
        self.devices = devices
        self.axes = axes
        self.lights = lights


class ScopeApp(Session):
    scope: AsDevice[Scope]
    recorder: AsPresenter[Recorder]


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
