"""The question spellings are ordinary types to a type checker.

Never imported or executed: pytest skips it and mypy checks it through
``files = "."``. The point of the aliases is that the short spelling costs
nothing statically, which only `assert_type` can observe.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, assert_type, runtime_checkable

from redsun.experimental import (
    DevicesOf,
    Requires,
    RequiresMaybe,
    RequiresOne,
    Session,
    satisfies,
)
from redsun.experimental.injection import constant


@runtime_checkable
class Resettable(Protocol):
    def reset(self) -> None: ...


@runtime_checkable
class HasCamera(Protocol):
    def apply_camera(self, zoom: float) -> None: ...


@runtime_checkable
class Movable(Protocol):
    async def move(self, position: float) -> None: ...


class Census:
    def __init__(self, name: str, /, resettable: Requires[Resettable]) -> None:
        self.name = name
        self.resettable = resettable

    def check(self) -> None:
        assert_type(self.resettable, Mapping[str, Resettable])
        for component in self.resettable.values():
            assert_type(component, Resettable)
            component.reset()


class Single:
    def __init__(self, name: str, /, camera: RequiresOne[HasCamera]) -> None:
        self.name = name
        self.camera = camera

    def check(self) -> None:
        assert_type(self.camera, HasCamera)
        self.camera.apply_camera(2.0)


class Optional:
    def __init__(self, name: str, /, camera: RequiresMaybe[HasCamera] = None) -> None:
        self.name = name
        self.camera = camera

    def check(self) -> None:
        assert_type(self.camera, HasCamera | None)
        # the narrowing a plain 'X | None' gets, so absence has to be handled
        if self.camera is not None:
            assert_type(self.camera, HasCamera)
            self.camera.apply_camera(2.0)


class DeviceCensus:
    def __init__(self, name: str, /, motors: DevicesOf[Movable]) -> None:
        self.name = name
        self.motors = motors

    async def check(self) -> None:
        assert_type(self.motors, Mapping[str, Movable])
        for device in self.motors.values():
            assert_type(device, Movable)
            await device.move(1.0)


def check_satisfying_types_what_it_returns(session: Session) -> None:
    assert_type(session.satisfying(Resettable), dict[str, Resettable])
    for component in session.satisfying(HasCamera).values():
        component.apply_camera(2.0)


def check_satisfies_narrows_an_instance_but_not_a_class(
    component: object, cls: type
) -> None:
    if satisfies(component, Resettable):
        assert_type(component, Resettable)
        component.reset()
    if satisfies(cls, Resettable):
        assert_type(cls, type)


def check_a_constant_answers_with_the_type_it_holds(component: Resettable) -> None:
    assert_type(constant(component), Callable[[], Resettable])
