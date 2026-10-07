"""Plans whose signatures "How to choose the inputs of a plan" shows."""

from __future__ import annotations

import enum
from collections.abc import Sequence  # noqa: TC003
from functools import cached_property
from typing import Annotated, Any, Literal

from annotated_types import Ge, Gt, Le, MaxLen, MultipleOf
from bluesky.protocols import Movable, Readable  # noqa: TC002
from bluesky.utils import MsgGenerator  # noqa: TC002
from ophyd_async.core import (
    Device,
    MovableLogic,
    StandardMovable,
    StandardReadable,
    soft_signal_rw,
)


class MyDetector(StandardReadable):
    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.counts = soft_signal_rw(int, 0)
        super().__init__(name=name)


class MyMotor(StandardReadable, StandardMovable[float]):
    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, 0.0, units="mm")
        super().__init__(name=name)

    @cached_property
    def movable_logic(self) -> MovableLogic[float]:
        return MovableLogic(setpoint=self.position, readback=self.position)


class Binning(enum.Enum):
    ONE = 1
    TWO = 2
    FOUR = 4


# --8<-- [start:values]
def snap(
    exposure: float = 0.1, frames: int = 10, label: str = "scan"
) -> MsgGenerator[None]:
    # --8<-- [end:values]
    yield from ()


# --8<-- [start:choices]
def bin_frames(
    mode: Literal["fast", "slow"] = "fast", binning: Binning = Binning.TWO
) -> MsgGenerator[None]:
    # --8<-- [end:choices]
    yield from ()


# --8<-- [start:devices]
def scan(
    detectors: Sequence[Readable[Any]],
    motor: Movable[float],
    exposure: float = 0.1,
    frames: int = 10,
) -> MsgGenerator[None]:
    # --8<-- [end:devices]
    yield from ()


# --8<-- [start:lists]
def walk(positions: list[float] = [0.0, 0.5, 1.0]) -> MsgGenerator[None]:
    # --8<-- [end:lists]
    yield from ()


# --8<-- [start:optional]
def acquire(frames: int | None = None) -> MsgGenerator[None]:
    # --8<-- [end:optional]
    yield from ()


# --8<-- [start:mapping]
def amplify(gains: dict[str, float] = {"x": 1.0, "y": 2.0}) -> MsgGenerator[None]:
    # --8<-- [end:mapping]
    yield from ()


# --8<-- [start:union]
def pause_between(delay: float | list[float] = 0.0) -> MsgGenerator[None]:
    # --8<-- [end:union]
    yield from ()


# --8<-- [start:limits]
def expose(
    frames: Annotated[int, Ge(1)] = 1,
    exposure: Annotated[float, Gt(0), Le(10), MultipleOf(0.001)] = 0.1,
    points: Annotated[list[float], MaxLen(3)] = [0.0, 1.0],
) -> MsgGenerator[None]:
    # --8<-- [end:limits]
    yield from ()


PLANS = {
    "values": snap,
    "choices": bin_frames,
    "devices": scan,
    "lists": walk,
    "optional": acquire,
    "mapping": amplify,
    "union": pause_between,
    "limits": expose,
}
"""Each tab of the reference section, with the plan it pictures."""


def devices() -> dict[str, Device]:
    """Return the devices the Devices tab offers."""
    return {"camera": MyDetector("camera"), "stage": MyMotor("stage")}
