"""The question spellings are ordinary types to a type checker.

Never imported or executed: pytest skips it and mypy checks it through
``files = "."``. The point of the aliases is that the short spelling costs
nothing statically, which only `assert_type` can observe.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, assert_type, runtime_checkable

from redsun.experimental import DevicesOf, Requires, RequiresMaybe, RequiresOne


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
