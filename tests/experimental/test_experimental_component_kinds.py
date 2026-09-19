"""A presenter takes part in a session whatever builds its constructor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, NewType, cast

import pydantic
import pytest
from ophyd_async.core import StandardReadable
from psygnal import Signal

from redsun.experimental import (
    AsDevice,
    AsPresenter,
    DeviceMapping,
    Session,
    provides,
    slot,
)

if TYPE_CHECKING:
    from .conftest import BuildSession

Readings = NewType("Readings", "dict[str, float]")
Label = NewType("Label", str)

CONFIG: dict[str, Any] = {
    "presenters": {"ctrl": {"gain": 7.5}},
    "wiring": [
        {"from": "ctrl.sig_moved", "to": "listener.on_move"},
        {"from": "listener.sig_step", "to": "ctrl.set_gain"},
    ],
}


class Stage(StandardReadable):
    pass


class Behaviour:
    """What the presenters below do, whichever way their constructor is made.

    It has no ``__slots__``, so a subclass has a ``__dict__``; `SlottedCtrl`
    repeats these members instead of inheriting them.
    """

    if TYPE_CHECKING:
        name: str
        devices: DeviceMapping
        gain: float
        _label: Label | None
        sig_moved: ClassVar[Signal]

    @property
    def label(self) -> Label | None:
        return self._label

    def setup(self, label: Label) -> None:
        self._label = label

    @slot
    def set_gain(self, gain: float) -> None:
        self.gain = gain

    @provides
    def readings(self) -> Readings:
        return Readings({name: self.gain for name in self.devices})

    def serialize(self) -> dict[str, float]:
        return {"gain": self.gain}


class PlainCtrl(Behaviour):
    sig_moved = Signal(str)

    def __init__(self, name: str, *, devices: DeviceMapping, gain: float = 1.0) -> None:
        self.name = name
        self.devices = devices
        self.gain = gain
        self._label = None


@dataclass
class DataclassCtrl(Behaviour):
    name: str
    devices: DeviceMapping
    gain: float = 1.0
    _label: Label | None = field(default=None, init=False)
    sig_moved = Signal(str)


@dataclass(kw_only=True)
class KwOnlyCtrl(Behaviour):
    name: str
    devices: DeviceMapping
    gain: float = 1.0
    _label: Label | None = field(default=None, init=False)
    sig_moved = Signal(str)


@dataclass(slots=True, weakref_slot=True)
class SlottedCtrl:
    name: str
    devices: DeviceMapping
    gain: float = 1.0
    _label: Label | None = field(default=None, init=False)
    sig_moved = Signal(str)

    @property
    def label(self) -> Label | None:
        return self._label

    def setup(self, label: Label) -> None:
        self._label = label

    @slot
    def set_gain(self, gain: float) -> None:
        self.gain = gain

    @provides
    def readings(self) -> Readings:
        return Readings({name: self.gain for name in self.devices})

    def serialize(self) -> dict[str, float]:
        return {"gain": self.gain}


class ModelCtrl(Behaviour, pydantic.BaseModel):
    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    name: str
    devices: DeviceMapping
    gain: float = 1.0
    _label: Label | None = pydantic.PrivateAttr(None)
    sig_moved: ClassVar[Signal] = Signal(str)


class Listener:
    sig_step = Signal(float)

    def __init__(self, name: str) -> None:
        self.name = name
        self.moves: list[str] = []
        self.readings: Readings | None = None

    def setup(self, readings: Readings) -> None:
        self.readings = readings

    @slot
    def on_move(self, where: str) -> None:
        self.moves.append(where)

    @provides
    def label(self) -> Label:
        return Label("from-listener")


class PlainApp(Session):
    motor: AsDevice[Stage]
    ctrl: AsPresenter[PlainCtrl]
    listener: AsPresenter[Listener]


class DataclassApp(Session):
    motor: AsDevice[Stage]
    ctrl: AsPresenter[DataclassCtrl]
    listener: AsPresenter[Listener]


class KwOnlyApp(Session):
    motor: AsDevice[Stage]
    ctrl: AsPresenter[KwOnlyCtrl]
    listener: AsPresenter[Listener]


class SlottedApp(Session):
    motor: AsDevice[Stage]
    ctrl: AsPresenter[SlottedCtrl]
    listener: AsPresenter[Listener]


class ModelApp(Session):
    motor: AsDevice[Stage]
    ctrl: AsPresenter[ModelCtrl]
    listener: AsPresenter[Listener]


@pytest.mark.parametrize(
    "app",
    [PlainApp, DataclassApp, KwOnlyApp, SlottedApp, ModelApp],
    ids=["plain", "dataclass", "kw-only-dataclass", "slotted-dataclass", "pydantic"],
)
def test_every_kind_of_class_takes_part_in_the_whole_session(
    app: type[Session], build: BuildSession
) -> None:
    """Configuration, devices, `setup`, `provides`, wiring and saving alike."""
    session = build(app, CONFIG)
    ctrl = cast("Behaviour | SlottedCtrl", session.presenters["ctrl"])
    listener = cast("Listener", session.presenters["listener"])

    assert ctrl.gain == 7.5
    assert dict(ctrl.devices) == {"motor": session.devices["motor"]}
    assert ctrl.label == "from-listener"
    assert listener.readings == {"motor": 7.5}

    ctrl.sig_moved.emit("left")
    listener.sig_step.emit(2.0)

    assert listener.moves == ["left"]
    assert session.serialize()["presenters"]["ctrl"] == {"gain": 2.0}


def test_a_model_refusing_its_configuration_is_skipped(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    session = build(ModelApp, {"presenters": {"ctrl": {"gain": "not a number"}}})

    assert "ctrl" not in session.presenters
    assert "validation error for ModelCtrl" in caplog.text
