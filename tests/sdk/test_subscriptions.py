from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from ophyd_async.core import soft_signal_rw

from redsun.aio import run_coro
from redsun.virtual import VirtualContainer, WiringError, slot

if TYPE_CHECKING:
    from ophyd_async.core import SignalRW


def put(signal: SignalRW[float], value: float) -> None:
    """Set a signal from the shared loop, the way a device would."""

    async def _set() -> None:
        await signal.set(value)

    run_coro(_set())


class Consumer:
    def __init__(self) -> None:
        self.readings: list[dict[str, Any]] = []

    @slot
    def absorb(self, reading: dict[str, Any]) -> None:
        self.readings.append(reading)

    def not_a_port(self, reading: dict[str, Any]) -> None: ...


def test_subscription_delivers_and_is_recorded() -> None:
    """A subscribed slot receives readings and both ends are named."""
    container = VirtualContainer()
    signal = soft_signal_rw(float, initial_value=0.0, name="base_dir")
    consumer = Consumer()
    container._set_components({"widget": consumer})

    record = container.subscribe(signal, consumer.absorb)
    put(signal, 1.0)

    assert str(record) == "base_dir ~> widget.absorb"
    assert container.subscriptions == [record]
    assert [r["base_dir"]["value"] for r in consumer.readings] == [0.0, 1.0]


def test_unmarked_method_cannot_be_subscribed() -> None:
    """The connectable surface is the same one 'connect' requires."""
    container = VirtualContainer()
    signal = soft_signal_rw(float, initial_value=0.0, name="base_dir")
    consumer = Consumer()

    with pytest.raises(WiringError, match="not connectable"):
        container.subscribe(signal, consumer.not_a_port)


def test_disconnect_all_releases_the_subscription() -> None:
    """Teardown stops delivery and empties the record."""
    container = VirtualContainer()
    signal = soft_signal_rw(float, initial_value=0.0, name="base_dir")
    consumer = Consumer()
    container.subscribe(signal, consumer.absorb)
    put(signal, 1.0)
    delivered = len(consumer.readings)

    container.disconnect_all()
    put(signal, 2.0)

    assert len(consumer.readings) == delivered
    assert container.subscriptions == []


def test_rebuilding_does_not_accumulate_subscribers() -> None:
    """The leak this exists to prevent: subscribe/release repeatedly."""
    container = VirtualContainer()
    signal = soft_signal_rw(float, initial_value=0.0, name="base_dir")
    consumer = Consumer()

    for _ in range(3):
        container.subscribe(signal, consumer.absorb)
        container.disconnect_all()

    consumer.readings.clear()
    container.subscribe(signal, consumer.absorb)
    put(signal, 1.0)

    # one initial reading plus one for the set, not four of each
    assert len(consumer.readings) == 2


@pytest.mark.parametrize("thread", ["current", "main"])
def test_thread_affinity_is_recorded(thread: str) -> None:
    """The subscription carries the affinity the delivery will use."""
    container = VirtualContainer()
    signal = soft_signal_rw(float, initial_value=0.0, name="base_dir")
    consumer = Consumer()

    record = container.subscribe(signal, consumer.absorb, thread=thread)  # type: ignore[arg-type]

    assert record.thread == thread
    assert str(record).endswith(f"[thread={thread}]")
