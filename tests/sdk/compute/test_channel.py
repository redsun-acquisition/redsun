"""A channel carries messages over a pipe, and large buffers through shared-memory rings."""

from __future__ import annotations

import logging
import multiprocessing
import sys
import threading
from importlib.util import find_spec
from typing import TYPE_CHECKING, Annotated, Any

import numpy as np
import pytest

from redsun.compute._channel import Channel, UnreadableMessage, rings

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

needs_sharedbox = pytest.mark.skipif(
    find_spec("sharedbox") is None, reason="needs sharedbox"
)

MIB = 1 << 20


def refuse() -> None:
    """Raise as unpickling a function the receiver cannot import does."""
    raise AttributeError("Can't get attribute 'fit' on <module '__main__'>")


class Unreadable:
    """A value that pickles and fails to unpickle."""

    def __reduce__(self) -> tuple[Callable[[], None], tuple[()]]:
        """Rebuild by calling `refuse`."""
        return (refuse, ())


@pytest.fixture
def channels() -> Iterator[tuple[Channel, Channel]]:
    """Return the two ends of a pipe as channels, and close both after the test."""
    a, b = multiprocessing.Pipe()
    sender, receiver = Channel(a), Channel(b)
    yield sender, receiver
    sender.close()
    receiver.close()


@pytest.fixture
def no_sharedbox(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make `sharedbox` fail to import, for the channels the test makes."""
    monkeypatch.setitem(sys.modules, "sharedbox", None)
    rings.cache_clear()
    yield
    rings.cache_clear()


def exchange(sender: Channel, receiver: Channel, *payloads: object) -> list[Any]:
    """Send each payload while *receiver* reads them on a thread; return what arrived."""
    received: list[Any] = []

    def read() -> None:
        for _ in payloads:
            received.append(receiver.receive())

    thread = threading.Thread(target=read)
    thread.start()
    for index, payload in enumerate(payloads):
        sender.send("result", index, payload)
    thread.join(timeout=10)
    assert [(kind, id) for kind, id, _ in received] == [
        ("result", index) for index in range(len(payloads))
    ]
    return [payload for _, _, payload in received]


def test_a_small_buffer_stays_in_the_pickle(
    channels: tuple[Channel, Channel],
) -> None:
    """Send a 1 KiB array through the pipe alone, with no ring."""
    sender, receiver = channels
    array = np.arange(256, dtype=np.uint32)

    (received,) = exchange(sender, receiver, array)

    assert np.array_equal(received, array)
    assert sender.ring_bytes == 0


@needs_sharedbox
def test_a_large_buffer_travels_through_a_ring_that_grows(
    channels: tuple[Channel, Channel],
) -> None:
    """Size the ring to the first large buffer and double it for a larger one."""
    sender, receiver = channels
    sizes = []
    for size in (MIB, MIB + MIB // 2, 5 * MIB):
        array = np.arange(size, dtype=np.uint8)
        (received,) = exchange(sender, receiver, array)
        assert np.array_equal(received, array)
        sizes.append(sender.ring_bytes)

    assert sizes == [MIB, 2 * MIB, 5 * MIB]


@needs_sharedbox
def test_more_buffers_than_ring_slots_arrive_in_order(
    channels: tuple[Channel, Channel],
) -> None:
    """Receive a payload holding six large arrays, more than the ring holds at once."""
    sender, receiver = channels
    arrays = [np.full(MIB, index, dtype=np.uint8) for index in range(6)]

    (received,) = exchange(sender, receiver, arrays)

    assert [int(array[0]) for array in received] == list(range(6))
    assert all(np.array_equal(a, b) for a, b in zip(received, arrays, strict=True))


@needs_sharedbox
def test_closing_unlinks_every_ring(channels: tuple[Channel, Channel]) -> None:
    """Leave no ring attachable after both ends close."""
    box = rings()
    assert box is not None
    a, b = channels
    exchange(a, b, np.zeros(MIB, dtype=np.uint8))
    exchange(b, a, np.zeros(MIB, dtype=np.uint8))
    names = a.ring_names | b.ring_names

    a.close()
    b.close()

    assert len(names) == 2
    item = Annotated[np.ndarray, box.MaxShape((MIB,)), box.DType("uint8")]
    for name in names:
        with pytest.raises(box.SegmentNotFoundError):
            box.SharedStream.attach(item, name)


@pytest.mark.usefixtures("no_sharedbox")
def test_without_sharedbox_buffers_stay_in_the_pickle(
    channels: tuple[Channel, Channel], caplog: pytest.LogCaptureFixture
) -> None:
    """Send a large array through the pipe and name the extra once, when sharedbox cannot import."""
    caplog.set_level(logging.INFO, logger="redsun")
    sender, receiver = channels
    array = np.arange(MIB, dtype=np.uint8)

    received = exchange(sender, receiver, array, array)

    assert all(np.array_equal(r, array) for r in received)
    assert sender.ring_bytes == 0
    assert [r.levelno for r in caplog.records if "redsun[sharedbox]" in r.message] == [
        logging.INFO
    ]


def test_receive_raises_eoferror_once_the_other_end_closes(
    channels: tuple[Channel, Channel],
) -> None:
    """Raise EOFError from receive after the other end closed."""
    sender, receiver = channels

    sender.close()

    with pytest.raises(EOFError):
        receiver.receive()


def test_an_unreadable_message_names_its_id_and_the_next_one_arrives(
    channels: tuple[Channel, Channel],
) -> None:
    """Raise UnreadableMessage with the kind and id of a payload that fails to unpickle, then read on."""
    sender, receiver = channels
    errors: list[UnreadableMessage] = []
    received: list[tuple[str, int, Any]] = []

    def read() -> None:
        try:
            receiver.receive()
        except UnreadableMessage as error:
            errors.append(error)
        received.append(receiver.receive())

    thread = threading.Thread(target=read)
    thread.start()
    sender.send("call", 7, (np.negative, (np.zeros(MIB, np.uint8), Unreadable()), {}))
    sender.send("result", 8, "next")
    thread.join(timeout=10)

    (error,) = errors
    assert (error.kind, error.id, type(error.error)) == ("call", 7, AttributeError)
    assert received == [("result", 8, "next")]


@needs_sharedbox
def test_a_send_waiting_on_a_full_ring_ends_when_the_other_end_closes(
    channels: tuple[Channel, Channel],
) -> None:
    """Raise EOFError from a send waiting for ring room once the other end closes its pipe."""
    sender, receiver = channels
    exchange(sender, receiver, np.zeros(MIB, dtype=np.uint8))
    failures: list[Exception] = []

    def send() -> None:
        try:
            sender.send("result", 1, [np.zeros(MIB, np.uint8) for _ in range(6)])
        except Exception as error:  # noqa: BLE001 - the test checks which one
            failures.append(error)

    thread = threading.Thread(target=send)
    thread.start()
    receiver.connection.recv()
    receiver.connection.close()
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert [type(error) for error in failures] == [EOFError]


@needs_sharedbox
def test_a_receive_waiting_on_ring_items_ends_when_the_other_end_closes(
    channels: tuple[Channel, Channel],
) -> None:
    """Raise EOFError from a receive whose sender closed before sending every ring item."""
    sender, receiver = channels
    exchange(sender, receiver, np.zeros(MIB, dtype=np.uint8))
    failures: list[Exception] = []

    def receive() -> None:
        try:
            receiver.receive()
        except Exception as error:  # noqa: BLE001 - the test checks which one
            failures.append(error)

    thread = threading.Thread(target=receive, daemon=True)
    thread.start()
    sender.connection.send(("result", 1, b"", 2))
    sender.send_item(np.zeros(MIB, dtype=np.uint8))
    sender.close()
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert [type(error) for error in failures] == [EOFError]
