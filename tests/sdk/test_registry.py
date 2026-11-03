from __future__ import annotations

from typing import Annotated, NewType, Protocol

import pytest

from redsun.errors import RegistrationError
from redsun.injection import Registry
from redsun.injection._registry import SESSION


class Motor:
    def move(self) -> None: ...


class Moves(Protocol):
    def move(self) -> None: ...


class Base: ...


class Derived(Base): ...


class Unbuilt:
    def __init__(self) -> None:
        raise AssertionError("the registry built a class nobody registered")


Named = NewType("Named", Motor)


def test_a_registry_answers_every_key_it_holds() -> None:
    """Call a factory on each request and fill a callable from the keys held."""
    registry = Registry()
    motor = Motor()
    reads: list[int] = []

    def count() -> int:
        reads.append(1)
        return len(reads)

    registry.register(Named, lambda: motor, owner="stage")
    registry.register(int, count, owner=SESSION)

    def build(
        *,
        stage: Named,
        count: int,
        maybe: Named | None,
        label: str | None,
        step: float = 1.0,
    ) -> tuple[object, ...]:
        return stage, count, maybe, label, step

    assert [provider() for provider in registry.providers(int)] == [1]
    assert registry.call(build) == (motor, 2, motor, None, 1.0)
    assert registry.call(build, step=2.0)[1:] == (3, motor, None, 2.0)


@pytest.mark.parametrize("second", [Motor, Annotated[Motor, "a"]])
def test_a_second_value_under_a_key_is_refused_naming_both_owners(
    second: object,
) -> None:
    """Refuse a second registration under one key, metadata diwire ignores included, naming both owners."""
    registry = Registry()
    registry.register(Motor, Motor, owner="stage")
    with pytest.raises(RegistrationError, match="'stage'.*'other'"):
        registry.register(second, Motor, owner="other")


def test_a_key_nobody_registered_is_never_built() -> None:
    """Give no provider for a class nobody registered, and refuse a call needing it, naming each parameter."""
    registry = Registry()

    def build(*, unbuilt: Unbuilt, count: int) -> None: ...

    assert list(registry.providers(Unbuilt)) == []
    with pytest.raises(TypeError, match="'unbuilt'.*'count'"):
        registry.call(build)


def test_a_lookup_matches_its_key_exactly() -> None:
    """Answer neither a subclass nor a union from a value registered under a base class."""
    registry = Registry()
    registry.register(Base, Base, owner="stage")
    assert list(registry.providers(Derived)) == []
    assert list(registry.providers(Base | Motor)) == []


def test_a_none_for_a_required_parameter_counts_as_missing() -> None:
    """Refuse a `None` for a required parameter, and pass it to an optional one."""
    registry = Registry()
    registry.register(Motor, lambda: None, owner="stage")

    def required(*, motor: Motor) -> None: ...

    def optional(*, motor: Motor | None) -> Motor | None:
        return motor

    with pytest.raises(TypeError, match="'motor'"):
        registry.call(required)
    assert registry.call(optional) is None


def test_ask_is_asked_each_time_a_provider_is_called() -> None:
    """Ask for a key nobody registered on every call, with no provider while there is no answer."""
    motor = Motor()
    sealed: list[bool] = []
    asked: list[object] = []

    def ask(key: object) -> tuple[object] | None:
        asked.append(key)
        return (motor,) if sealed and key is Moves else None

    registry = Registry(ask)
    assert list(registry.providers(Moves)) == []
    sealed.append(True)
    [provider] = registry.providers(Moves)
    assert (provider(), provider()) == (motor, motor)
    assert asked == [Moves] * 4
