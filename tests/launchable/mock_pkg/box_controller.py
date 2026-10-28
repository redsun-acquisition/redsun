"""A FastCS controller covering every kind of attribute the sharedbox transport carries."""

from __future__ import annotations

import asyncio
import enum

import numpy as np
from fastcs.attributes import AttrR, AttrRW, AttrW
from fastcs.controllers import Controller, ControllerVector
from fastcs.datatypes import Enum, Float, Int, String, Table, Waveform
from fastcs.methods import command


class Mode(enum.Enum):
    """Choices of the `mode` attribute."""

    IDLE = 0
    RUN = 1


class Axis(Controller):
    """One element of the `axes` vector."""

    def __init__(self) -> None:
        super().__init__()
        self.position = AttrRW(Float(prec=3))


class BoxController(Controller):
    """Controller with a float, a string, a limited int, an enum, a command and a vector."""

    def __init__(self, put_delay: float = 0.0) -> None:
        super().__init__()
        self.put_delay = put_delay
        self.runs = 0
        self.exposure = AttrRW(Float(units="ms", min=0.0, prec=2))
        self.label = AttrR(String(length=8), initial_value="start")
        self.limited = AttrRW(Int(max=10))
        self.mode = AttrRW(Enum(Mode))
        self.trace = AttrRW(Waveform(np.int32, shape=(10,)))
        self.big = AttrRW(Int(min=0, max=2**64 - 1))
        self.slow_seen = 0
        self.slow = AttrW(Int())
        self.slow.set_on_put_callback(self.delayed_put)
        self.axes = ControllerVector({0: Axis(), 1: Axis()})

    async def initialise(self) -> None:
        """Yield once, as a controller reading its attributes from hardware does."""
        await asyncio.sleep(0)

    async def delayed_put(self, attr: AttrW[int], value: int) -> None:
        """Wait `put_delay` seconds, then store the value in `slow_seen`."""
        await asyncio.sleep(self.put_delay)
        self.slow_seen = value

    @command()
    async def run(self) -> None:
        """Count one run."""
        self.runs += 1


class TableController(Controller):
    """Controller with a table attribute, which the transport refuses."""

    def __init__(self) -> None:
        super().__init__()
        self.rows = AttrRW(Table([("a", "int32")]))
