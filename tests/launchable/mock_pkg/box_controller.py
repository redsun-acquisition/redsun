"""A FastCS controller covering every kind of attribute the sharedbox transport carries."""

from __future__ import annotations

import asyncio
import enum

import numpy as np
from fastcs.attributes import AttrR, AttrRW, AttrW
from fastcs.controllers import Controller, ControllerVector
from fastcs.datatypes import Bool, Enum, Float, Int, String, Table, Waveform
from fastcs.methods import command

from redsun.services.sharedbox import LabelledAttrRW


class Mode(enum.Enum):
    """Choices of the `mode` attribute."""

    IDLE = 0
    RUN = 1


class Axis(Controller):
    """One element of the `axes` vector."""

    def __init__(self) -> None:
        super().__init__()
        self.position = AttrRW(Float(prec=3))
        self.steps = AttrR(Int())


class BoxController(Controller):
    """Controller with a float, a string, a limited int, an enum, a command and a vector."""

    def __init__(self, put_delay: float = 0.0) -> None:
        super().__init__()
        self.put_delay = put_delay
        self.put_started = asyncio.Event()
        self.put_gate: asyncio.Event | None = None
        self.runs = 0
        self.exposure = LabelledAttrRW(
            Float(units="ms", min=0.0, prec=2),
            label="Exposure",
            description="How long each frame collects light.",
        )
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
        """Wait for `put_gate`, or `put_delay` seconds without one, then store the value."""
        self.put_started.set()
        if self.put_gate is None:
            await asyncio.sleep(self.put_delay)
        else:
            await self.put_gate.wait()
        self.slow_seen = value

    @command()
    async def run(self) -> None:
        """Count one run."""
        self.runs += 1


class Lasers(Controller):
    """Two switches."""

    def __init__(self) -> None:
        super().__init__()
        self.red = AttrRW(Bool())
        self.blue = AttrRW(Bool())


class Region(Controller):
    """The region a readout keeps."""

    def __init__(self) -> None:
        super().__init__()
        self.width = AttrRW(Int(), initial_value=8)


class Readout(Controller):
    """A readable and a writable setting, and a region below them."""

    def __init__(self) -> None:
        super().__init__()
        self.gain = AttrRW(Int())
        self.count = AttrR(Int(), initial_value=3)
        self.region = Region()


class BoardController(Controller):
    """A controller whose children devices take in different ways."""

    def __init__(self) -> None:
        super().__init__()
        self.exposure = AttrRW(Float())
        self.lasers = Lasers()
        self.detector = Readout()
        self.spare = Readout()


class IntExposureController(Controller):
    """Controller whose `exposure` is an integer, unlike the one of `BoxController`."""

    def __init__(self) -> None:
        super().__init__()
        self.exposure = AttrRW(Int())


class TableController(Controller):
    """Controller with a table attribute, which the transport refuses."""

    def __init__(self) -> None:
        super().__init__()
        self.rows = AttrRW(Table([("a", "int32")]))


class NamedController(Controller):
    """Controller with attributes named like `SharedBox` methods."""

    def __init__(self) -> None:
        super().__init__()
        self.name = AttrRW(Int())
        self.watch = AttrRW(Int())


class TextController(Controller):
    """A controller with a short writable string and commands that raise."""

    def __init__(self) -> None:
        super().__init__()
        self.text = AttrRW(String(length=4), initial_value="ab")

    @command()
    async def refuse(self) -> None:
        """Raise `RuntimeError`."""
        raise RuntimeError("busy")

    @command()
    async def refuse_silently(self) -> None:
        """Raise `RuntimeError` with no message."""
        raise RuntimeError
