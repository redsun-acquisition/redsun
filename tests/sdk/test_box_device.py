"""The device side of the sharedbox transport."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from uuid import uuid4

import numpy as np
import pytest
import pytest_asyncio
from fastcs.control_system import FastCS
from mock_pkg.box_controller import BoxController, IntExposureController
from ophyd_async.core import (
    Device,
    DeviceVector,
    SignalR,
    SignalRW,
    StrictEnum,
    TriggerableCommand,
    observe_value,
)

from redsun.device.sharedbox import BoxDeviceConnector, BoxPutError, stream_name
from redsun.services.sharedbox import BoxTransport


class MyDetector(Device):
    exposure: SignalRW[float]
    limited: SignalRW[int]
    run: TriggerableCommand

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
async def detector(
    served: tuple[BoxController, str],
) -> AsyncGenerator[MyDetector, None]:
    device = MyDetector(served[1], name="det")
    await device.connect(timeout=5)
    yield device
    for box in device._connector._boxes.values():  # type: ignore[attr-defined]
        box.close()


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
    """Fill each device with its declared children only, sharing the attributes."""
    controller, prefix = served
    exposer = Exposer(prefix, name="exposer")
    mover = Mover(prefix, name="mover")
    await exposer.connect(timeout=5)
    await mover.connect(timeout=5)
    try:
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
