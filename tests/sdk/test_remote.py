"""Tests for the `remote` marker."""

from __future__ import annotations

import asyncio
from collections.abc import Generator

import pytest
from psygnal import Signal

from redsun import remote, slot
from redsun.aio import clear_async_backend, set_async_backend
from redsun.ports._remote import is_remote


class Emitter:
    sig_value = Signal(int)


class Receiver:
    def __init__(self) -> None:
        self.received: list[int] = []

    @slot
    async def take(self, n: int) -> int:
        self.received.append(n)
        return n


@pytest.fixture
def async_backend() -> Generator[None, None, None]:
    set_async_backend()
    yield
    clear_async_backend()


def test_remote_marks_the_function_and_returns_it() -> None:
    """Return the function it is given, marked."""

    async def move(self: object, delta: float) -> float:
        return delta

    assert remote(move) is move
    assert is_remote(move)


@pytest.mark.parametrize(
    "target", [property(lambda self: 1), staticmethod(lambda: 1), len]
)
def test_remote_refuses_what_is_not_a_plain_function(target: object) -> None:
    """Refuse a property, a staticmethod or a builtin, naming where @remote goes."""
    with pytest.raises(TypeError, match="directly on the def"):
        remote(target)  # type: ignore[type-var]


def test_remote_refuses_a_function_already_marked_as_a_slot() -> None:
    """Refuse @remote placed above @slot."""

    async def move(self: object) -> None: ...

    with pytest.raises(TypeError, match="below @slot"):
        remote(slot(move))


async def test_a_slot_returning_a_value_receives_a_signal(
    async_backend: None,
) -> None:
    """Deliver an emission to an async slot that returns a value, dropping the value."""
    emitter, receiver = Emitter(), Receiver()
    emitter.sig_value.connect(receiver.take)
    emitter.sig_value.emit(3)
    for _ in range(100):
        if receiver.received:
            break
        await asyncio.sleep(0.01)
    assert receiver.received == [3]
