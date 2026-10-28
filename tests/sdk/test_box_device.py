"""The device side of the sharedbox transport."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from fastcs.control_system import FastCS
from mock_pkg.box_controller import BoxController
from ophyd_async.core import (
    Device,
    DeviceVector,
    SignalR,
    SignalRW,
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

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(name=name, connector=BoxDeviceConnector(prefix))


class WrongDatatype(Device):
    exposure: SignalRW[int]

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(name=name, connector=BoxDeviceConnector(prefix))


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
    for box in device._connector.boxes.values():  # type: ignore[attr-defined]
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


async def test_a_declared_child_missing_from_the_index_fails_connect(
    served: tuple[BoxController, str],
) -> None:
    """Name the missing child in the error."""
    device = MissingChild(served[1], name="bad")
    with pytest.raises(Exception, match="absent"):
        await device.connect(timeout=5)


async def test_a_declared_datatype_that_disagrees_fails_connect(
    served: tuple[BoxController, str],
) -> None:
    """Name the attribute whose declared datatype is not the served one."""
    device = WrongDatatype(served[1], name="bad")
    with pytest.raises(Exception, match="exposure"):
        await device.connect(timeout=5)


async def test_a_mock_connect_needs_no_service() -> None:
    """Connect a device with mock backends while no service runs."""
    device = MyDetector("NOBODY", name="det")
    await device.connect(mock=True)
    assert await device.exposure.get_value() == 0.0


async def test_a_connect_without_a_service_times_out() -> None:
    """Raise once the timeout passes with no index published."""
    device = MyDetector(f"T{uuid4().hex[:8]}", name="det")
    with pytest.raises(Exception, match="index"):
        await device.connect(timeout=0.3)


def test_stream_name_joins_prefix_and_part() -> None:
    """Join the prefix and the part with a colon."""
    assert stream_name("MYAPP:DET:", "frames") == "MYAPP:DET:frames"
