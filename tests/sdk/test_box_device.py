"""The device side of the sharedbox transport."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import numpy as np
import pytest
import pytest_asyncio
from fastcs.control_system import FastCS
from mock_pkg.board_controller import BoardController
from mock_pkg.box_controller import (
    BoxController,
    IntExposureController,
    NamedController,
    TextController,
)
from ophyd_async.core import (
    Device,
    DeviceMap,
    DeviceVector,
    NotConnectedError,
    SignalR,
    SignalRW,
    StrictEnum,
    TriggerableCommand,
    observe_value,
)
from sharedbox import BoxClosedError, RequestError, SegmentStatus

from redsun.device import sharedbox as box_device
from redsun.device.sharedbox import (
    AllServed,
    BoxDeviceConnector,
    BoxPutError,
    ServiceExitedError,
    stream_name,
)
from redsun.services._transports import SHAREDBOX, TRANSPORTS
from redsun.services.sharedbox import BoxTransport

if TYPE_CHECKING:
    from sharedbox import RequestFuture, SharedBox


class MyDetector(Device):
    exposure: SignalRW[float]
    limited: SignalRW[int]
    run: TriggerableCommand

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(name=name, connector=BoxDeviceConnector(prefix))


class Renamed(Device):
    watch: SignalRW[int]

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(
            name=name, connector=BoxDeviceConnector(prefix, declared_only=True)
        )


class MyTexter(Device):
    text: SignalRW[str]
    refuse: TriggerableCommand
    refuse_silently: TriggerableCommand

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(name=name, connector=BoxDeviceConnector(prefix))


class MissingChild(Device):
    absent: SignalR[int]

    def __init__(
        self, prefix: str, name: str = "", *, declared_only: bool = False
    ) -> None:
        super().__init__(
            name=name,
            connector=BoxDeviceConnector(prefix, declared_only=declared_only),
        )


class WrongDatatype(Device):
    exposure: SignalRW[int]

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(name=name, connector=BoxDeviceConnector(prefix))


class WrongMode(StrictEnum):
    IDLE = "IDLE"


class WrongEnum(Device):
    mode: SignalRW[WrongMode]

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(name=name, connector=BoxDeviceConnector(prefix))


class Axis(Device):
    position: SignalRW[float]
    speed: SignalR[float]


class Stage(Device):
    axes: DeviceVector[Axis]

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(name=name, connector=BoxDeviceConnector(prefix))


class Position(Device):
    position: SignalRW[float]


class Exposer(Device):
    exposure: SignalRW[float]
    run: TriggerableCommand

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(
            name=name, connector=BoxDeviceConnector(prefix, declared_only=True)
        )


class Mover(Device):
    exposure: SignalRW[float]
    axes: DeviceVector[Position]

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(
            name=name, connector=BoxDeviceConnector(prefix, declared_only=True)
        )


class Spare(Device):
    gain: SignalRW[int]


class Board(Device):
    exposure: SignalRW[float]
    lasers: DeviceMap[SignalRW[bool]]
    detector: AllServed
    spare: Spare

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(
            name=name, connector=BoxDeviceConnector(prefix, declared_only=True)
        )


class MixedMap(Device):
    detector: DeviceMap[SignalRW[int]]

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(
            name=name, connector=BoxDeviceConnector(prefix, declared_only=True)
        )


@pytest_asyncio.fixture
async def served() -> AsyncGenerator[tuple[BoxController, str], None]:
    prefix = f"T{uuid4().hex[:8]}"
    controller = BoxController(put_delay=0.3)
    controller.set_path([prefix])
    fastcs = FastCS(controller, [BoxTransport()], loop=asyncio.get_running_loop())
    task = asyncio.create_task(fastcs.serve(interactive=False))
    yield controller, prefix
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest_asyncio.fixture
async def texter() -> AsyncGenerator[tuple[TextController, MyTexter], None]:
    prefix = f"T{uuid4().hex[:8]}"
    controller = TextController()
    controller.set_path([prefix])
    fastcs = FastCS(controller, [BoxTransport()], loop=asyncio.get_running_loop())
    task = asyncio.create_task(fastcs.serve(interactive=False))
    device = MyTexter(prefix, name="text")
    await device.connect(timeout=5)
    yield controller, device
    for box in device._connector._boxes.values():  # type: ignore[attr-defined]
        box.close()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest_asyncio.fixture
async def detector(
    served: tuple[BoxController, str],
) -> AsyncGenerator[MyDetector, None]:
    device = MyDetector(served[1], name="det")
    await device.connect(timeout=5)
    yield device
    for box in device._connector._boxes.values():  # type: ignore[attr-defined]
        box.close()


@pytest_asyncio.fixture
async def board_served() -> AsyncGenerator[tuple[BoardController, str], None]:
    prefix = f"T{uuid4().hex[:8]}"
    controller = BoardController()
    controller.set_path([prefix])
    fastcs = FastCS(controller, [BoxTransport()], loop=asyncio.get_running_loop())
    task = asyncio.create_task(fastcs.serve(interactive=False))
    yield controller, prefix
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest_asyncio.fixture
async def board(
    board_served: tuple[BoardController, str],
) -> AsyncGenerator[Board, None]:
    device = Board(board_served[1], name="board")
    await device.connect(timeout=5)
    yield device
    device._connector.close()  # type: ignore[attr-defined]


async def test_a_device_is_filled_from_the_index(detector: MyDetector) -> None:
    """Create the undeclared children and keep the declared ones."""
    assert isinstance(detector.exposure, SignalRW)
    assert await detector.exposure.get_value() == 0.0
    assert await detector.label.get_value() == "start"  # type: ignore[attr-defined]
    assert isinstance(detector.axes, DeviceVector)  # type: ignore[attr-defined]
    assert sorted(detector.axes.keys()) == [0, 1]  # type: ignore[attr-defined]
    assert isinstance(detector.axes[1].position, SignalRW)  # type: ignore[attr-defined]


async def test_set_round_trips(
    served: tuple[BoxController, str], detector: MyDetector
) -> None:
    """Write each kind of value and read it back, from the service as well."""
    controller, _ = served
    await detector.exposure.set(2.5)
    assert controller.exposure.get() == 2.5
    assert await detector.exposure.get_value() == 2.5
    await detector.axes[1].position.set(4.0)  # type: ignore[attr-defined]
    assert await detector.axes[1].position.get_value() == 4.0  # type: ignore[attr-defined]
    await detector.big.set(2**64 - 1)  # type: ignore[attr-defined]
    assert await detector.big.get_value() == 2**64 - 1  # type: ignore[attr-defined]
    mode = await detector.mode.get_value()  # type: ignore[attr-defined]
    await detector.mode.set(type(mode)("RUN"))  # type: ignore[attr-defined]
    assert controller.mode.get().name == "RUN"
    assert (await detector.mode.get_value()).value == "RUN"  # type: ignore[attr-defined]


async def test_a_short_waveform_round_trips(
    served: tuple[BoxController, str], detector: MyDetector
) -> None:
    """Keep the length of a waveform shorter than the field on both sides."""
    controller, _ = served
    sent = np.array([1, 2, 3], dtype=np.int32)
    await detector.trace.set(sent)  # type: ignore[attr-defined]
    np.testing.assert_array_equal(controller.trace.get(), sent)
    np.testing.assert_array_equal(await detector.trace.get_value(), sent)  # type: ignore[attr-defined]


async def test_a_reading_carries_the_time_the_service_published(
    served: tuple[BoxController, str], detector: MyDetector
) -> None:
    """Stamp a reading with the box's timestamp, not the session's clock."""
    controller, _ = served
    await controller.exposure.update(3.0)
    reading = (await detector.exposure.read())["det-exposure"]
    box = detector._connector._boxes[""]  # type: ignore[attr-defined]
    assert reading["value"] == 3.0
    assert reading["timestamp"] == box.exposure.timestamp_ns / 1e9


async def test_a_short_waveform_set_from_the_session_keeps_its_shape(
    detector: MyDetector,
) -> None:
    """Read a waveform shorter than its maximum back with the shape it was set with."""
    await detector.trace.set(np.array([4, 5, 6], dtype=np.int32))  # type: ignore[attr-defined]
    assert (await detector.trace.get_value()).shape == (3,)  # type: ignore[attr-defined]
    box = detector._connector._boxes[""]  # type: ignore[attr-defined]
    assert box.trace.read()["setpoint"].shape == (3,)


@pytest.mark.parametrize("choice", ["member", "name"])
async def test_an_enum_is_set_by_member_or_by_name(
    served: tuple[BoxController, str], detector: MyDetector, choice: str
) -> None:
    """Set an enum signal from one of its members or from the name of one."""
    controller, _ = served
    member = type(await detector.mode.get_value())("RUN")  # type: ignore[attr-defined]
    await detector.mode.set(member if choice == "member" else "RUN")  # type: ignore[attr-defined]
    assert controller.mode.get().name == "RUN"


async def test_a_string_longer_than_its_field_is_refused_before_sending(
    texter: tuple[TextController, MyTexter],
) -> None:
    """Raise ValueError naming the attribute and leave the service's value alone."""
    controller, device = texter
    with pytest.raises(ValueError, match="text"):
        await device.text.set("too long for it")
    assert controller.text.get() == "ab"


async def test_a_command_the_service_refuses_raises_its_message(
    texter: tuple[TextController, MyTexter],
) -> None:
    """Raise BoxPutError carrying the message of the exception the command raised."""
    _, device = texter
    with pytest.raises(BoxPutError, match="busy") as caught:
        await device.refuse.trigger()
    assert caught.value.attribute == "refuse"
    assert str(caught.value) == "refuse: busy"


async def test_a_command_that_raises_without_a_message_gives_its_type(
    texter: tuple[TextController, MyTexter],
) -> None:
    """Raise BoxPutError with the exception type when the exception has no message."""
    _, device = texter
    with pytest.raises(BoxPutError) as caught:
        await device.refuse_silently.trigger()
    assert str(caught.value) == "refuse_silently: RuntimeError"


async def test_a_box_its_service_unlinked_raises_service_exited(
    detector: MyDetector, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Raise ServiceExitedError from a read when the box's segment is missing."""
    monkeypatch.setattr(
        "redsun.device.sharedbox.segment_status", lambda name: SegmentStatus.MISSING
    )
    with pytest.raises(ServiceExitedError):
        await detector.exposure.get_value()


async def test_a_command_its_service_unlinked_raises_service_exited(
    detector: MyDetector, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Raise ServiceExitedError from a command when the service has stopped."""
    monkeypatch.setattr(
        "redsun.device.sharedbox.segment_status",
        lambda name: SegmentStatus.CREATOR_EXITED,
    )
    with pytest.raises(ServiceExitedError):
        await detector.run.trigger()


async def test_a_subscribe_while_the_service_is_down_leaves_the_signal_subscribable(
    served: tuple[BoxController, str],
    detector: MyDetector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deliver readings to a subscriber made after the service stopped, and subscribe again later."""
    controller, _ = served
    while_down: asyncio.Queue[float] = asyncio.Queue()
    later: asyncio.Queue[float] = asyncio.Queue()

    def collect_while_down(reading: dict[str, Any]) -> None:
        while_down.put_nowait(next(iter(reading.values()))["value"])

    def collect_later(reading: dict[str, Any]) -> None:
        later.put_nowait(next(iter(reading.values()))["value"])

    with monkeypatch.context() as down:
        down.setattr(
            "redsun.device.sharedbox.segment_status",
            lambda name: SegmentStatus.CREATOR_EXITED,
        )
        detector.exposure.subscribe_reading(collect_while_down)
        assert await asyncio.wait_for(while_down.get(), 5) == 0.0
        await controller.exposure.update(5.0)
        assert await asyncio.wait_for(while_down.get(), 5) == 5.0
        detector.exposure.clear_sub(collect_while_down)
    detector.exposure.subscribe_reading(collect_later)
    assert await asyncio.wait_for(later.get(), 5) == 5.0


async def test_a_subscriber_that_raises_leaves_the_signal_subscribable(
    detector: MyDetector,
) -> None:
    """Accept a new callback after the first one raised while taking the current reading."""
    backend = detector.exposure._connector.backend
    received: list[Any] = []

    def refuse(reading: Any) -> None:
        raise ValueError("refused")

    with pytest.raises(ValueError, match="refused"):
        backend.set_callback(refuse)
    backend.set_callback(received.append)
    backend.set_callback(None)
    assert len(received) == 1


async def test_locate_gives_the_setpoint_and_the_readback(
    served: tuple[BoxController, str], detector: MyDetector
) -> None:
    """Return the value last set as the setpoint and the service's value as the readback."""
    controller, _ = served
    await detector.exposure.set(2.5)
    await controller.exposure.update(3.0)
    async with asyncio.timeout(5):
        while (await detector.exposure.locate())["readback"] != 3.0:
            await asyncio.sleep(0.005)
    assert await detector.exposure.locate() == {"setpoint": 2.5, "readback": 3.0}
    label = detector.label._connector.backend  # type: ignore[attr-defined]
    assert await label.get_location() == {"setpoint": "start", "readback": "start"}


async def test_an_observer_sees_nothing_for_a_refused_set(
    detector: MyDetector,
) -> None:
    """Deliver no reading for a write the service refused, only for the next accepted one."""
    readings: asyncio.Queue[int] = asyncio.Queue()

    def collect(reading: dict[str, Any]) -> None:
        readings.put_nowait(next(iter(reading.values()))["value"])

    detector.limited.subscribe_reading(collect)
    assert await asyncio.wait_for(readings.get(), 5) == 0
    with pytest.raises(BoxPutError):
        await detector.limited.set(11)
    await detector.limited.set(3)
    assert await asyncio.wait_for(readings.get(), 5) == 3
    detector.limited.clear_sub(collect)


async def test_a_waveform_that_does_not_fit_is_refused_before_sending(
    served: tuple[BoxController, str], detector: MyDetector
) -> None:
    """Raise ValueError naming the attribute and leave the service's waveform alone."""
    controller, _ = served
    before = np.array(controller.trace.get())
    for value in (np.zeros(11, dtype=np.int32), np.zeros((2, 2), dtype=np.int32)):
        with pytest.raises(ValueError, match="trace"):
            await detector.trace.set(value)  # type: ignore[attr-defined]
    np.testing.assert_array_equal(controller.trace.get(), before)


async def test_an_unknown_enum_name_is_refused_naming_the_attribute_and_choices(
    served: tuple[BoxController, str], detector: MyDetector
) -> None:
    """Raise ValueError naming the attribute and the names the enum has."""
    controller, _ = served
    with pytest.raises(ValueError, match=r"mode.*'FAST'.*IDLE.*RUN"):
        await detector.mode.set("FAST")  # type: ignore[attr-defined]
    assert controller.mode.get().name == "IDLE"


async def test_a_write_from_another_writer_supersedes_with_put_error(
    served: tuple[BoxController, str],
    detector: MyDetector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise BoxPutError for a write that another device's write replaces before the service takes it."""
    controller, prefix = served
    sent: asyncio.Queue[str] = asyncio.Queue()
    answered = box_device._answered

    async def spy(box: SharedBox, attribute: str, request: RequestFuture[Any]) -> Any:
        sent.put_nowait(attribute)
        return await answered(box, attribute, request)

    monkeypatch.setattr("redsun.device.sharedbox._answered", spy)
    second = MyDetector(prefix, name="second")
    third = MyDetector(prefix, name="third")
    await second.connect(timeout=5)
    await third.connect(timeout=5)
    gate = asyncio.Event()
    controller.put_gate = gate
    try:
        holding = asyncio.ensure_future(detector.slow.set(1, timeout=10))  # type: ignore[attr-defined]
        await asyncio.wait_for(sent.get(), 5)
        await asyncio.wait_for(controller.put_started.wait(), 5)
        replaced = asyncio.ensure_future(second.slow.set(2, timeout=10))  # type: ignore[attr-defined]
        await asyncio.wait_for(sent.get(), 5)
        replacing = asyncio.ensure_future(third.slow.set(3, timeout=10))  # type: ignore[attr-defined]
        await asyncio.wait_for(sent.get(), 5)
        gate.set()
        results = await asyncio.gather(
            holding, replaced, replacing, return_exceptions=True
        )
    finally:
        gate.set()
        for device in (second, third):
            for box in device._connector._boxes.values():  # type: ignore[attr-defined]
                box.close()
    assert results[0] is None
    assert isinstance(results[1], BoxPutError)
    assert "superseded by another writer" in str(results[1])
    assert results[2] is None


async def test_an_attribute_named_like_a_box_method_is_read_and_written() -> None:
    """Write and read an attribute whose box field has a trailing underscore."""
    prefix = f"T{uuid4().hex[:8]}"
    controller = NamedController()
    controller.set_path([prefix])
    fastcs = FastCS(controller, [BoxTransport()], loop=asyncio.get_running_loop())
    task = asyncio.create_task(fastcs.serve(interactive=False))
    device = Renamed(prefix, name="renamed")
    try:
        await device.connect(timeout=5)
        await device.watch.set(5)
        assert controller.watch.get() == 5
        await controller.watch.update(6)
        async with asyncio.timeout(5):
            async for value in observe_value(device.watch):
                if value == 6:
                    break
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for box in device._connector._boxes.values():  # type: ignore[attr-defined]
            box.close()


async def test_a_request_cut_by_a_stopping_service_reports_the_service_exited(
    detector: MyDetector, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Raise ServiceExitedError, not a BoxPutError naming the box class, for a request the stopping service cut."""
    box = detector._connector._boxes[""]  # type: ignore[attr-defined]

    async def cut() -> None:
        raise RequestError("ControllerBox.exposure: the server stopped")

    with pytest.raises(BoxPutError) as running:
        await box_device._answered(box, "exposure", cut())  # type: ignore[arg-type]
    assert str(running.value) == "exposure: the server stopped"

    monkeypatch.setattr(
        "redsun.device.sharedbox.segment_status",
        lambda name: SegmentStatus.CREATOR_EXITED,
    )
    with pytest.raises(ServiceExitedError):
        await box_device._answered(box, "exposure", cut())  # type: ignore[arg-type]


async def test_a_refused_set_raises_with_the_service_message(
    detector: MyDetector,
) -> None:
    """Raise BoxPutError naming the attribute, with FastCS's text."""
    with pytest.raises(BoxPutError, match="11") as caught:
        await detector.limited.set(11)
    assert caught.value.attribute == "limited"
    assert await detector.limited.get_value() == 0


async def test_two_sets_on_one_signal_each_get_their_own_answer(
    detector: MyDetector,
) -> None:
    """Pair each of two concurrent sets with its own error."""
    good, refused = await asyncio.gather(
        detector.limited.set(3), detector.limited.set(11), return_exceptions=True
    )
    assert good is None
    assert isinstance(refused, BoxPutError)
    assert await detector.limited.get_value() == 3


async def test_a_set_after_a_timed_out_one_pairs_with_its_own_request(
    served: tuple[BoxController, str], detector: MyDetector
) -> None:
    """Wait for the service to answer the later set, not the stale one."""
    controller, _ = served
    slow = detector.slow  # type: ignore[attr-defined]
    with pytest.raises(TimeoutError):
        await slow.set(1, timeout=0.05)
    await slow.set(2, timeout=5)
    assert controller.slow_seen == 2


async def test_a_command_is_triggered(
    served: tuple[BoxController, str], detector: MyDetector
) -> None:
    """Run the command in the service and return once it is done."""
    controller, _ = served
    await detector.run.trigger()
    assert controller.runs == 1


async def test_observe_value_follows_a_readback(
    served: tuple[BoxController, str], detector: MyDetector
) -> None:
    """Yield each value the service publishes."""
    controller, _ = served
    seen: list[str] = []
    async with asyncio.timeout(5):
        async for value in observe_value(detector.label):  # type: ignore[attr-defined]
            seen.append(value)
            if value == "start":
                await controller.label.update("next")
            if value == "next":
                break
    assert seen == ["start", "next"]


async def test_describe_carries_units_and_limits(detector: MyDetector) -> None:
    """Report the units, precision and control limits the service described."""
    key = (await detector.exposure.describe())["det-exposure"]
    assert key["units"] == "ms"
    assert key["precision"] == 2
    assert key["limits"]["control"]["low"] == 0.0
    choices = (await detector.mode.describe())["det-mode"]["choices"]  # type: ignore[attr-defined]
    assert choices == ["IDLE", "RUN"]


async def test_describe_carries_the_served_description_only_when_given(
    detector: MyDetector,
) -> None:
    """Put the description the service served in the data key, and no key when it served none."""
    exposure = (await detector.exposure.describe())["det-exposure"]
    mode = (await detector.mode.describe())["det-mode"]  # type: ignore[attr-defined]
    assert exposure.get("description") == "How long each frame collects light."
    assert "description" not in mode


async def test_describe_carries_the_served_label_only_when_given(
    board: Board,
) -> None:
    """Put the label the service served in the data key, and no key when it served none."""
    exposure = (await board.exposure.describe())["board-exposure"]
    gain = (await board.spare.gain.describe())["board-spare-gain"]
    assert exposure.get("label") == "Exposure"
    assert "label" not in gain


@pytest.mark.parametrize("declared_only", [False, True])
async def test_a_declared_child_missing_from_the_index_fails_connect(
    served: tuple[BoxController, str], declared_only: bool
) -> None:
    """Name the missing child in the error, whether undeclared ones are filled or not."""
    device = MissingChild(served[1], name="bad", declared_only=declared_only)
    with pytest.raises(Exception, match="absent"):
        await device.connect(timeout=5)


async def test_a_declared_datatype_that_disagrees_fails_connect(
    served: tuple[BoxController, str],
) -> None:
    """Name the attribute whose declared datatype is not the served one."""
    device = WrongDatatype(served[1], name="bad")
    with pytest.raises(Exception, match="exposure"):
        await device.connect(timeout=5)


async def test_a_declared_enum_that_disagrees_fails_connect(
    served: tuple[BoxController, str],
) -> None:
    """Refuse a declared enum whose members differ from the served names."""
    device = WrongEnum(served[1], name="bad")
    with pytest.raises(Exception, match="mode"):
        await device.connect(timeout=5)


async def test_a_declared_signal_missing_from_a_child_fails_connect(
    served: tuple[BoxController, str],
) -> None:
    """Name a signal a child device declares and its controller does not serve."""
    device = Stage(served[1], name="bad")
    with pytest.raises(Exception, match="speed"):
        await device.connect(timeout=5)


async def test_devices_on_one_service_fill_only_what_they_declare(
    served: tuple[BoxController, str],
) -> None:
    """Fill and attach each device with its declared children only, sharing the attributes."""
    controller, prefix = served
    exposer = Exposer(prefix, name="exposer")
    mover = Mover(prefix, name="mover")
    await exposer.connect(timeout=5)
    await mover.connect(timeout=5)
    try:
        assert sorted(exposer._connector._boxes) == [""]  # type: ignore[attr-defined]
        assert sorted(mover._connector._boxes) == ["", "axes:0", "axes:1"]  # type: ignore[attr-defined]
        assert sorted(name for name, _ in exposer.children()) == ["exposure", "run"]
        assert sorted(name for name, _ in mover.children()) == ["axes", "exposure"]
        assert sorted(mover.axes.keys()) == [0, 1]
        assert [name for name, _ in mover.axes[1].children()] == ["position"]
        await exposer.exposure.set(3.5)
        assert await mover.exposure.get_value() == 3.5
        await mover.axes[1].position.set(2.0)
        assert controller.axes[1].position.get() == 2.0
        await exposer.run.trigger()
        assert controller.runs == 1
    finally:
        for device in (exposer, mover):
            for box in device._connector._boxes.values():  # type: ignore[attr-defined]
                box.close()


async def test_an_observer_survives_a_reconnect(
    served: tuple[BoxController, str], detector: MyDetector
) -> None:
    """Keep yielding values after the connector attaches the boxes again."""
    controller, _ = served
    seen: list[float] = []
    async with asyncio.timeout(5):
        async for value in observe_value(detector.exposure):
            seen.append(value)
            if len(seen) == 1:
                await detector.connect(timeout=5, force_reconnect=True)
                await controller.exposure.update(7.0)
            if value == 7.0:
                break
    assert seen[-1] == 7.0


async def test_release_closes_the_boxes_a_device_attached(
    served: tuple[BoxController, str], detector: MyDetector
) -> None:
    """Refuse a read after the transport is released, and serve one after a reconnect."""
    await TRANSPORTS[SHAREDBOX].release()

    with pytest.raises(BoxClosedError):
        await detector.exposure.get_value()
    await detector.connect(timeout=5, force_reconnect=True)
    assert await detector.exposure.get_value() == 0.0


async def test_a_device_reconnects_after_the_service_restarts() -> None:
    """Reach a restarted service and keep an observer running across the restart."""
    prefix = f"T{uuid4().hex[:8]}"
    controller = BoxController()
    controller.set_path([prefix])
    fastcs = FastCS(controller, [BoxTransport()], loop=asyncio.get_running_loop())
    task = asyncio.create_task(fastcs.serve(interactive=False))
    device = MyDetector(prefix, name="det")
    await device.connect(timeout=5)
    seen: asyncio.Queue[float] = asyncio.Queue()

    async def observe() -> None:
        async for value in observe_value(device.exposure):
            seen.put_nowait(value)

    observer = asyncio.create_task(observe())
    assert await asyncio.wait_for(seen.get(), 5) == 0.0
    first_source = device.exposure.source
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    restarted = BoxController()
    restarted.set_path([prefix])
    fastcs = FastCS(restarted, [BoxTransport()], loop=asyncio.get_running_loop())
    task = asyncio.create_task(fastcs.serve(interactive=False))
    try:
        await device.connect(timeout=5, force_reconnect=True)
        await device.exposure.set(1.5)
        assert restarted.exposure.get() == 1.5
        assert device.exposure.source != first_source
        assert device.exposure.source.startswith(f"sharedbox://{prefix}:fastcs:")
        await restarted.exposure.update(9.0)
        async with asyncio.timeout(5):
            while await seen.get() != 9.0:
                pass
    finally:
        observer.cancel()
        task.cancel()
        await asyncio.gather(observer, task, return_exceptions=True)
        for box in device._connector._boxes.values():  # type: ignore[attr-defined]
            box.close()


async def test_a_reconnect_refuses_a_service_whose_layout_changed() -> None:
    """Raise when a restarted service serves another datatype than the device was filled from."""
    prefix = f"T{uuid4().hex[:8]}"
    controller = BoxController()
    controller.set_path([prefix])
    fastcs = FastCS(controller, [BoxTransport()], loop=asyncio.get_running_loop())
    task = asyncio.create_task(fastcs.serve(interactive=False))
    device = MyDetector(prefix, name="det")
    await device.connect(timeout=5)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    changed = IntExposureController()
    changed.set_path([prefix])
    fastcs = FastCS(changed, [BoxTransport()], loop=asyncio.get_running_loop())
    task = asyncio.create_task(fastcs.serve(interactive=False))
    try:
        with pytest.raises(RuntimeError, match="built again"):
            await device.connect(timeout=5, force_reconnect=True)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for box in device._connector._boxes.values():  # type: ignore[attr-defined]
            box.close()


async def test_a_mock_connect_needs_no_service() -> None:
    """Connect a device with mock backends while no service runs."""
    device = MyDetector("NOBODY", name="det")
    await device.connect(mock=True)
    assert await device.exposure.get_value() == 0.0


def test_creating_children_twice_keeps_the_first_ones() -> None:
    """Leave the declared children in place when the connector is asked again."""

    class Stage(Device):
        exposure: SignalRW[float]

    connector = BoxDeviceConnector("NOBODY")
    device = Stage(connector=connector)
    exposure = device.exposure
    connector.create_children_from_annotations(device)
    assert device.exposure is exposure


async def test_a_connect_without_a_service_times_out() -> None:
    """Raise once the timeout passes with no index published."""
    device = MyDetector(f"T{uuid4().hex[:8]}", name="det")
    with pytest.raises(Exception, match="index"):
        await device.connect(timeout=0.3)


def test_stream_name_joins_prefix_and_part() -> None:
    """Join the prefix and the part with a colon."""
    assert stream_name("MYAPP:DET:", "frames") == "MYAPP:DET:frames"


async def test_a_declared_map_takes_every_attribute_of_its_controller(
    board_served: tuple[BoardController, str], board: Board
) -> None:
    """Fill a declared map with one entry per served attribute, and write through one."""
    controller, _ = board_served
    assert sorted(board.lasers.keys()) == ["blue", "red"]
    await board.lasers["red"].set(True)
    assert controller.lasers.red.get() is True


async def test_a_map_refuses_an_attribute_of_another_signal_type(
    board_served: tuple[BoardController, str],
) -> None:
    """Fail connect, naming the read-only attribute a map of writable signals cannot hold."""
    device = MixedMap(board_served[1], name="bad")
    with pytest.raises(NotConnectedError, match="count"):
        await device.connect(timeout=5)


async def test_a_child_that_takes_all_served_gets_its_whole_subtree(
    board_served: tuple[BoardController, str], board: Board
) -> None:
    """Fill an `AllServed` child with everything below it, and a sibling with what it declares."""
    controller, _ = board_served
    detector: Any = board.detector
    assert isinstance(detector.gain, SignalRW)
    assert await detector.count.get_value() == 3
    await detector.region.width.set(16)
    assert controller.detector.region.width.get() == 16
    assert [name for name, _ in board.spare.children()] == ["gain"]


async def test_a_map_and_an_all_served_child_connect_empty_in_mock_mode() -> None:
    """Connect a device declaring a map and an `AllServed` child without a service."""
    device = Board("absent", name="board")
    await device.connect(mock=True)
    assert dict(device.lasers) == {}
    assert list(device.detector.children()) == []
