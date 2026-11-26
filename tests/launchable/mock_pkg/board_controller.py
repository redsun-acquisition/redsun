"""A FastCS controller whose children a device fills in different ways, with a labelled attribute."""

from __future__ import annotations

from fastcs.attributes import AttrR, AttrRW
from fastcs.controllers import Controller
from fastcs.datatypes import Bool, Float, Int

from redsun.services.sharedbox import LabelledAttrRW


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
        self.exposure = LabelledAttrRW(Float(), label="Exposure")
        self.lasers = Lasers()
        self.detector = Readout()
        self.spare = Readout()
