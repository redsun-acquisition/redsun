from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, ClassVar

import pytest
from psygnal import SignalGroup

# psygnal re-exports get/set_async_backend at the top level but not this one
from psygnal._async import clear_async_backend

from redsun.aio import set_async_backend
from redsun.virtual import (
    Signal,
    SlotThread,
    VirtualContainer,
    WiringError,
    ports,
    slot,
)


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


def test_connect_delivers_and_records() -> None:
    """A connection carries emissions and shows both ends of the link."""
    container = VirtualContainer()
    producer, consumer = Producer(), Consumer()
    container._set_components({"prod": producer, "cons": consumer})

    link = container.connect(producer.sig_new_data, consumer._update_layers)

    assert str(link) == "prod.sig_new_data -> cons.frames  [thread=main]"
    assert container.connections == [link]
    producer.sig_new_data.emit(FrameBatch("cam", {"a": 1}))
    assert consumer.seen == [FrameBatch("cam", {"a": 1})]


def test_undecorated_method_is_not_connectable() -> None:
    """Only a marked method is part of the connectable surface."""
    container = VirtualContainer()
    producer, consumer = Producer(), Consumer()

    with pytest.raises(WiringError, match="not connectable"):
        container.connect(producer.sig_untyped, consumer.not_a_port)


@pytest.mark.parametrize("port", ["wrong_arity", "wrong_payload"])
def test_incompatible_slot_is_rejected(port: str) -> None:
    """A typed signal checks both the count and the type of the arguments."""
    container = VirtualContainer()
    producer, consumer = Producer(), Consumer()
    container._set_components({"prod": producer, "cons": consumer})

    with pytest.raises(
        WiringError, match=f"cannot connect prod.sig_new_data -> cons.{port}"
    ):
        container.connect(producer.sig_new_data, getattr(consumer, port))


@pytest.mark.parametrize(
    ("port", "override", "expected"),
    [
        ("_update_layers", None, "main"),
        ("overrides_thread", None, "current"),
        ("_update_layers", "current", "current"),
    ],
)
def test_thread_affinity(port: str, override: SlotThread, expected: str) -> None:
    """The class declares the affinity; the slot and the call site override it."""
    container = VirtualContainer()
    producer, consumer = Producer(), Consumer()

    link = container.connect(
        producer.sig_new_data, getattr(consumer, port), thread=override
    )

    assert link.thread == expected


def test_disconnect_all_stops_delivery() -> None:
    """Teardown undoes every connection the container made."""
    container = VirtualContainer()
    producer, consumer = Producer(), Consumer()
    container.connect(producer.sig_new_data, consumer._update_layers)
    producer.sig_new_data.emit(FrameBatch("cam", {"a": 1}))

    container.disconnect_all()
    producer.sig_new_data.emit(FrameBatch("cam", {"b": 2}))

    assert len(consumer.seen) == 1
    assert container.connections == []


def test_ports_lists_the_public_surface() -> None:
    """Public signals and marked methods are ports; nothing else is."""
    surface = ports(Consumer())
    producer_surface = ports(Producer())

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


def test_grouped_signals_are_ports_under_their_member_name() -> None:
    """A signal group contributes its members, not the group attribute."""
    surface = ports(Grouped())

    assert sorted(surface.signals) == ["filtered", "median"]


def test_unknown_component_falls_back_to_its_class_name() -> None:
    """A signal whose owner was never registered still labels the link."""
    container = VirtualContainer()
    producer, consumer = Producer(), Consumer()

    link = container.connect(producer.sig_new_data, consumer._update_layers)

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


def test_a_coroutine_slot_is_connected_and_dispatched() -> None:
    """An async method is a slot like any other; psygnal dispatches it."""

    class AsyncConsumer:
        def __init__(self) -> None:
            self.seen: list[FrameBatch] = []

        @slot
        async def absorb(self, batch: FrameBatch) -> None:
            self.seen.append(batch)

    container = VirtualContainer()
    producer, consumer = Producer(), AsyncConsumer()
    set_async_backend()
    try:
        link = container.connect(producer.sig_new_data, consumer.absorb)
        producer.sig_new_data.emit(FrameBatch("cam", {"a": 1}))

        deadline = time.perf_counter() + 5.0
        while not consumer.seen and time.perf_counter() < deadline:
            time.sleep(0.005)
    finally:
        container.disconnect_all()
        clear_async_backend()

    assert link.consumer_port == "absorb"
    assert consumer.seen == [FrameBatch("cam", {"a": 1})]
