"""Tests for a session writing back out the configuration that rebuilds it."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

import pytest
from ophyd_async.core import Device

from redsun.experimental import AppContainer, AsDevice, AsPresenter


class Stage(Device):
    """Device writing back the axis it was configured with."""

    def __init__(self, name: str, /, axis: str = "X") -> None:
        super().__init__(name=name)
        self.axis = axis

    def serialize(self) -> dict[str, Any]:
        return {"axis": self.axis}


@dataclass
class Ctrl:
    """Presenter whose settings are exactly its constructor's parameters."""

    name: str
    step: float = 5.0
    timeout: float = 2.0

    def serialize(self) -> dict[str, Any]:
        return {"step": self.step, "timeout": self.timeout}


class Quiet:
    """Presenter serializing nothing, so whatever the file said is kept."""

    def __init__(self, name: str, /, gain: float = 1.0) -> None:
        self.name = name
        self.gain = gain


class Renamed:
    """Presenter asking to save a key its own constructor would refuse."""

    def __init__(self, name: str, /, step: float = 1.0) -> None:
        self.name = name
        self.step = step

    def serialize(self) -> dict[str, Any]:
        return {"stepsize": self.step}


class Anything:
    """Presenter whose constructor accepts every key, through ``**kwargs``."""

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        self.name = name
        self.kwargs = kwargs

    def serialize(self) -> dict[str, Any]:
        return {"whatever": 1}


class App(AppContainer):
    __slots__ = ()

    config: ClassVar[Mapping[str, Any]] = {
        "schema_version": 1.0,
        "name": "round-trip",
        "devices": {"stage": {"axis": "Z"}},
        "presenters": {"ctrl": {"step": 7.5}, "quiet": {"gain": 3.0}},
    }

    stage: AsDevice[Stage]
    ctrl: AsPresenter[Ctrl]
    quiet: AsPresenter[Quiet]


class RefusingApp(AppContainer):
    __slots__ = ()

    config: ClassVar[Mapping[str, Any]] = {
        "name": "refusing",
        "presenters": {"renamed": {"step": 4.0}, "anything": {"whatever": 0}},
    }

    renamed: AsPresenter[Renamed]
    anything: AsPresenter[Anything]


def test_a_changed_session_rebuilds_from_what_it_wrote() -> None:
    session = App().build()
    session.ctrl.step = 9.0
    session.stage.axis = "Y"
    written = session.serialize()
    session.shutdown()

    rebuilt = App(written).build()

    assert rebuilt.ctrl.step == 9.0
    assert rebuilt.stage.axis == "Y"
    assert rebuilt.serialize() == written
    rebuilt.shutdown()


def test_serialize_writes_a_parameter_no_source_named() -> None:
    session = App().build()

    assert session.serialize()["presenters"]["ctrl"] == {"step": 7.5, "timeout": 2.0}
    session.shutdown()


def test_a_component_serializing_nothing_keeps_the_entry_it_loaded() -> None:
    session = App().build()
    session.quiet.gain = 8.0

    assert session.serialize()["presenters"]["quiet"] == {"gain": 3.0}
    session.shutdown()


def test_an_entry_the_constructor_would_refuse_is_dropped_whole(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = RefusingApp().build()

    with caplog.at_level(logging.WARNING, logger="redsun"):
        written = session.serialize()

    assert written["presenters"]["renamed"] == {"step": 4.0}
    assert (
        "'renamed' tried to save stepsize, which Renamed does not accept" in caplog.text
    )
    session.shutdown()


def test_a_constructor_taking_kwargs_accepts_every_key() -> None:
    session = RefusingApp().build()

    assert session.serialize()["presenters"]["anything"] == {"whatever": 1}
    session.shutdown()


def test_a_session_nobody_has_touched_has_no_changes() -> None:
    session = App().build()

    assert not session.has_changes()
    session.shutdown()


def test_a_component_asking_to_be_written_differently_is_a_change() -> None:
    session = App().build()
    session.ctrl.step = 9.0

    assert session.has_changes()
    session.shutdown()


def test_a_value_changed_and_changed_back_reads_as_unchanged() -> None:
    session = App().build()
    session.ctrl.step = 9.0
    session.ctrl.step = 7.5

    assert not session.has_changes()
    session.shutdown()


def test_a_component_that_serializes_nothing_never_changes() -> None:
    session = App().build()
    session.quiet.gain = 8.0

    assert not session.has_changes()
    session.shutdown()


def test_a_refused_key_still_counts_as_a_change() -> None:
    session = RefusingApp().build()
    session.renamed.step = 9.0

    assert session.has_changes()
    session.shutdown()
