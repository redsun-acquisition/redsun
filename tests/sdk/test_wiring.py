from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from ophyd_async.core import soft_signal_rw
from psygnal import SignalGroup
from psygnal._async import clear_async_backend

from redsun.aio import set_async_backend
from redsun.virtual import (
    Signal,
    SlotThread,
    WiringError,
    ports,
    slot,
)

if TYPE_CHECKING:
    from redsun.virtual import VirtualContainer


@dataclass(frozen=True)
class FrameBatch:
    key: str
    data: dict[str, Any]


class Producer:
    sig_new_data = Signal(FrameBatch, check_types_on_connect=True)
    sig_untyped = Signal(object)
    _sig_private = Signal(object)


class FrameSignals(SignalGroup, strict=True):
    median = Signal(object)
    filtered = Signal(object)


class Grouped:
    def __init__(self) -> None:
        self.frames = FrameSignals(instance=self)


class Consumer:
    __redsun_slot_thread__: ClassVar[SlotThread] = "main"

    def __init__(self) -> None:
        self.seen: list[FrameBatch] = []

    @slot(name="frames")
    def _update_layers(self, batch: FrameBatch) -> None:
        self.seen.append(batch)

    @slot
    def bare(self, batch: FrameBatch) -> None: ...

    @slot(thread="current")
    def overrides_thread(self, batch: FrameBatch) -> None: ...

    @slot
    def wrong_arity(self, batch: FrameBatch, extra: int) -> None: ...

    @slot
    def wrong_payload(self, batch: int) -> None: ...

    def not_a_port(self, batch: FrameBatch) -> None: ...


class AsyncConsumer:
    def __init__(self) -> None:
        self.seen: list[FrameBatch] = []

    @slot
    async def absorb(self, batch: FrameBatch) -> None:
        self.seen.append(batch)


@pytest.fixture
def producer() -> Producer:
    return Producer()


@pytest.fixture
def consumer() -> Consumer:
    return Consumer()


@pytest.fixture
def named(
    bus: VirtualContainer, producer: Producer, consumer: Consumer
) -> VirtualContainer:
    """Return the bus with the producer named ``prod`` and the consumer ``cons``."""
    bus._set_components({"prod": producer, "cons": consumer})
    return bus


def test_connect_delivers_and_records(
    named: VirtualContainer, producer: Producer, consumer: Consumer
) -> None:
    """A connection carries emissions and shows both ends of the link."""
    link = named.connect(producer.sig_new_data, consumer._update_layers)

    assert str(link) == "prod.sig_new_data -> cons.frames  [thread=main]"
    assert named.connections == [link]
    producer.sig_new_data.emit(FrameBatch("cam", {"a": 1}))
    assert consumer.seen == [FrameBatch("cam", {"a": 1})]


def test_undecorated_method_is_not_connectable(
    bus: VirtualContainer, producer: Producer, consumer: Consumer
) -> None:
    """Only a marked method is part of the connectable surface."""
    with pytest.raises(WiringError, match="not connectable"):
        bus.connect(producer.sig_untyped, consumer.not_a_port)


@pytest.mark.parametrize("port", ["wrong_arity", "wrong_payload"])
def test_incompatible_slot_is_rejected(
    named: VirtualContainer, producer: Producer, consumer: Consumer, port: str
) -> None:
    """A typed signal checks both the count and the type of the arguments."""
    with pytest.raises(
        WiringError, match=f"cannot connect prod.sig_new_data -> cons.{port}"
    ):
        named.connect(producer.sig_new_data, getattr(consumer, port))


@pytest.mark.parametrize(
    ("port", "override", "expected"),
    [
        ("_update_layers", None, "main"),
        ("overrides_thread", None, "current"),
        ("_update_layers", "current", "current"),
    ],
)
def test_thread_affinity(
    bus: VirtualContainer,
    producer: Producer,
    consumer: Consumer,
    port: str,
    override: SlotThread,
    expected: str,
) -> None:
    """The class declares the affinity; the slot and the call site override it."""
    link = bus.connect(producer.sig_new_data, getattr(consumer, port), thread=override)

    assert link.thread == expected


def test_disconnect_all_stops_delivery(
    bus: VirtualContainer, producer: Producer, consumer: Consumer
) -> None:
    """Teardown undoes every connection the container made."""
    bus.connect(producer.sig_new_data, consumer._update_layers)
    producer.sig_new_data.emit(FrameBatch("cam", {"a": 1}))

    bus.disconnect_all()
    producer.sig_new_data.emit(FrameBatch("cam", {"b": 2}))

    assert len(consumer.seen) == 1
    assert bus.connections == []


def test_ports_lists_the_public_surface(producer: Producer, consumer: Consumer) -> None:
    """Public signals and marked methods are ports; nothing else is."""
    surface = ports(consumer)
    producer_surface = ports(producer)

    assert sorted(surface.slots) == [
        "bare",
        "frames",
        "overrides_thread",
        "wrong_arity",
        "wrong_payload",
    ]
    assert surface.signals == {}
    assert sorted(producer_surface.signals) == ["sig_new_data", "sig_untyped"]
    assert producer_surface.slots == {}


def test_unconnected_lists_what_nothing_reaches(
    named: VirtualContainer, producer: Producer, consumer: Consumer
) -> None:
    """The complement of the recorded links, as component.port paths."""
    named.connect(producer.sig_new_data, consumer._update_layers)

    report = named.unconnected

    assert report.signals == ["prod.sig_untyped"]
    assert sorted(report.slots) == [
        "cons.bare",
        "cons.overrides_thread",
        "cons.wrong_arity",
        "cons.wrong_payload",
    ]
    assert report
    assert "prod.sig_untyped -> nothing" in str(report)
    assert "nothing -> cons.bare" in str(report)


def test_a_subscribed_slot_counts_as_connected(
    bus: VirtualContainer, consumer: Consumer
) -> None:
    """A device subscription reaches a slot the same way a connection does."""
    bus._set_components({"cons": consumer})
    signal = soft_signal_rw(float, initial_value=0.0, name="base_dir")
    bus.subscribe(signal, consumer.bare)

    assert "cons.bare" not in bus.unconnected.slots


def test_a_fully_wired_container_reports_nothing(bus: VirtualContainer) -> None:
    """The empty case is falsy and says so."""
    bus._set_components({})

    report = bus.unconnected

    assert not report
    assert str(report) == "every port is connected"


def test_grouped_signals_are_ports_under_their_member_name() -> None:
    """A signal group contributes its members, not the group attribute."""
    surface = ports(Grouped())

    assert sorted(surface.signals) == ["filtered", "median"]


def test_unknown_component_falls_back_to_its_class_name(
    bus: VirtualContainer, producer: Producer, consumer: Consumer
) -> None:
    """A signal whose owner was never registered still labels the link."""
    link = bus.connect(producer.sig_new_data, consumer._update_layers)

    assert link.publisher == "Producer"
    assert link.consumer == "Consumer"


def test_a_group_member_clashing_with_a_signal_is_rejected() -> None:
    """One port namespace: a member cannot shadow a signal of the same name."""

    class Clashing:
        median = Signal(object)

        def __init__(self) -> None:
            self.frames = FrameSignals(instance=self)

    with pytest.raises(WiringError, match="two signals named 'median'"):
        ports(Clashing())


def test_a_coroutine_slot_is_connected_and_dispatched(
    bus: VirtualContainer, producer: Producer
) -> None:
    """An async method is a slot like any other; psygnal dispatches it."""
    consumer = AsyncConsumer()
    set_async_backend()
    try:
        link = bus.connect(producer.sig_new_data, consumer.absorb)
        producer.sig_new_data.emit(FrameBatch("cam", {"a": 1}))

        deadline = time.perf_counter() + 5.0
        while not consumer.seen and time.perf_counter() < deadline:
            time.sleep(0.005)
    finally:
        bus.disconnect_all()
        clear_async_backend()

    assert link.consumer_port == "absorb"
    assert consumer.seen == [FrameBatch("cam", {"a": 1})]
