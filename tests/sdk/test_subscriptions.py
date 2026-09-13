from __future__ import annotations

from typing import TYPE_CHECKING, Any

import psygnal
import pytest
from ophyd_async.core import soft_signal_rw

from redsun.aio import run_coro
from redsun.virtual import WiringError, slot

if TYPE_CHECKING:
    from ophyd_async.core import SignalRW

    from redsun.virtual import VirtualContainer


class Consumer:
    def __init__(self) -> None:
        self.readings: list[dict[str, Any]] = []

    @slot
    def absorb(self, reading: dict[str, Any]) -> None:
        self.readings.append(reading)

    def not_a_port(self, reading: dict[str, Any]) -> None: ...


@pytest.fixture
def signal() -> SignalRW[float]:
    return soft_signal_rw(float, initial_value=0.0, name="base_dir")


@pytest.fixture
def consumer() -> Consumer:
    return Consumer()


def put(signal: SignalRW[float], value: float) -> None:
    """Set a signal from the shared loop, the way a device would."""

    async def _set() -> None:
        await signal.set(value)

    run_coro(_set())


def test_subscription_delivers_and_is_recorded(
    bus: VirtualContainer, signal: SignalRW[float], consumer: Consumer
) -> None:
    """A subscribed slot receives readings and both ends are named."""
    bus._set_components({"widget": consumer})

    record = bus.subscribe(signal, consumer.absorb)
    put(signal, 1.0)

    assert str(record) == "base_dir ~> widget.absorb"
    assert bus.subscriptions == [record]
    assert [r["base_dir"]["value"] for r in consumer.readings] == [0.0, 1.0]


def test_unmarked_method_cannot_be_subscribed(
    bus: VirtualContainer, signal: SignalRW[float], consumer: Consumer
) -> None:
    """The connectable surface is the same one 'connect' requires."""
    with pytest.raises(WiringError, match="not connectable"):
        bus.subscribe(signal, consumer.not_a_port)


def test_disconnect_all_releases_the_subscription(
    bus: VirtualContainer, signal: SignalRW[float], consumer: Consumer
) -> None:
    """Teardown stops delivery and empties the record."""
    bus.subscribe(signal, consumer.absorb)
    put(signal, 1.0)
    delivered = len(consumer.readings)

    bus.disconnect_all()
    put(signal, 2.0)

    assert len(consumer.readings) == delivered
    assert bus.subscriptions == []


def test_rebuilding_does_not_accumulate_subscribers(
    bus: VirtualContainer, signal: SignalRW[float], consumer: Consumer
) -> None:
    """The leak this exists to prevent: subscribe/release repeatedly."""
    for _ in range(3):
        bus.subscribe(signal, consumer.absorb)
        bus.disconnect_all()

    consumer.readings.clear()
    bus.subscribe(signal, consumer.absorb)
    put(signal, 1.0)

    # one initial reading plus one for the set, not four of each
    assert len(consumer.readings) == 2


@pytest.mark.parametrize("thread", ["current", "main"])
def test_thread_affinity_delays_delivery_to_that_thread(
    bus: VirtualContainer, signal: SignalRW[float], consumer: Consumer, thread: str
) -> None:
    """The reading arrives from the shared loop and waits for the slot's thread."""
    record = bus.subscribe(signal, consumer.absorb, thread=thread)  # type: ignore[arg-type]

    assert record.thread == thread
    assert str(record).endswith(f"[thread={thread}]")
    assert consumer.readings == []
    psygnal.emit_queued()
    assert len(consumer.readings) == 1
