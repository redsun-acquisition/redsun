"""Tests for the `remote` marker."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest
from psygnal import Signal

from redsun import remote, slot
from redsun.aio import clear_async_backend, set_async_backend
from redsun.ports._remote import is_remote, served, signal_schema

if TYPE_CHECKING:
    from decimal import Decimal


class Emitter:
    sig_value = Signal(int)


class Receiver:
    def __init__(self) -> None:
        self.received: list[int] = []

    @slot
    async def take(self, n: int) -> int:
        self.received.append(n)
        return n


class Good:
    sig_moved = Signal(str, float)
    sig_any = Signal(str, object)

    @property
    @remote
    def state(self) -> dict[str, float]:
        return {}

    @slot
    @remote
    async def move(self, axis: str, delta: float) -> float:
        return delta

    @slot
    async def hidden(self) -> None: ...


class NotASlot:
    @remote
    async def go(self) -> None: ...


class SyncSlot:
    @slot
    @remote
    def go(self) -> None: ...


class AsyncGetter:
    @property
    @remote
    async def state(self) -> int:
        return 1


class Unresolvable:
    @slot
    @remote
    async def go(self, value: Decimal) -> None: ...


class Plain:
    def __init__(self, x: int) -> None:
        self.x = x


class NoSchema:
    @slot
    @remote
    async def go(self, value: Plain) -> None: ...


class Unmarked:
    sig_value = Signal(int)

    @slot
    async def go(self) -> None: ...


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


def test_served_lists_remote_members_and_every_public_signal() -> None:
    """Return the remote slots and properties, and all public signals, by name."""
    s = served(Good())
    assert s is not None
    assert [c.name for c in s.commands] == ["move"]
    assert [q.name for q in s.queries] == ["state"]
    assert set(s.signals) == {"sig_moved", "sig_any"}
    assert s.commands[0].parameters == {"axis": str, "delta": float}
    assert s.commands[0].returns is float


async def test_served_binds_the_command_and_the_query_to_the_instance() -> None:
    """Call the command and read the query on the instance they were listed from."""
    s = served(Good())
    assert s is not None
    assert await s.commands[0].call("x", 2.0) == 2.0
    assert s.queries[0].read() == {}


def test_a_component_with_nothing_remote_is_not_served() -> None:
    """Return None for a component with no remote member."""
    assert served(Unmarked()) is None


@pytest.mark.parametrize(
    ("cls", "message"),
    [
        (NotASlot, "'go' is @remote but not a @slot"),
        (SyncSlot, "'go' is a remote slot and must be async def"),
        (AsyncGetter, "'state' is a remote property with an async getter"),
        (Unresolvable, "'go' has annotations that do not resolve"),
        (NoSchema, "'go' takes a type with no JSON Schema"),
    ],
)
def test_served_refuses_each_rule_naming_the_member(cls: type, message: str) -> None:
    """Refuse each broken rule with an error naming the member."""
    with pytest.raises(TypeError, match=re.escape(message)):
        served(cls())


def test_an_object_argument_is_published_untyped() -> None:
    """Describe an object-typed signal argument with an empty schema."""
    s = served(Good())
    assert s is not None
    assert signal_schema(s)["sig_any"] == [{"type": "string"}, {}]
