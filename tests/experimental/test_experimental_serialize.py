"""Tests for a session writing back out the configuration that rebuilds it."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from ophyd_async.core import Device

from redsun.experimental import AppContainer, AsDevice, AsPresenter

if TYPE_CHECKING:
    from collections.abc import Callable


class Stage(Device):
    """Device writing back the axis it was configured with."""

    def __init__(self, name: str, /, axis: str = "X") -> None:
        super().__init__(name=name)
        self.axis = axis

    def serialize(self) -> dict[str, str]:
        return {"axis": self.axis}


@dataclass
class Ctrl:
    """Presenter whose settings are exactly its constructor's parameters."""

    name: str
    step: float = 5.0
    timeout: float = 2.0

    def serialize(self) -> dict[str, float]:
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

    def serialize(self) -> dict[str, float]:
        return {"stepsize": self.step}


class Anything:
    """Presenter whose constructor accepts every key, through ``**kwargs``."""

    def __init__(self, name: str, /, **kwargs: object) -> None:
        self.name = name
        self.kwargs = kwargs

    def serialize(self) -> dict[str, int]:
        return {"whatever": 1}


class App(AppContainer):
    __slots__ = ()

    config: ClassVar[dict[str, Any]] = {
        "schema_version": 1.0,
        "name": "round-trip",
        "devices": {"stage": {"axis": "Z"}},
        "presenters": {
            "ctrl": {"step": 7.5},
            "quiet": {"gain": 3.0},
            "renamed": {"step": 4.0},
            "anything": {"whatever": 0},
        },
    }

    stage: AsDevice[Stage]
    ctrl: AsPresenter[Ctrl]
    quiet: AsPresenter[Quiet]
    renamed: AsPresenter[Renamed]
    anything: AsPresenter[Anything]


def test_a_changed_session_rebuilds_from_what_it_wrote(
    build: Callable[..., AppContainer],
) -> None:
    session = build(App)
    session.ctrl.step = 9.0
    session.stage.axis = "Y"
    written = session.serialize()
    session.shutdown()

    rebuilt = build(App, written)

    assert rebuilt.ctrl.step == 9.0
    assert rebuilt.stage.axis == "Y"
    assert rebuilt.serialize() == written


def test_serialize_writes_a_parameter_no_source_named(
    build: Callable[..., AppContainer],
) -> None:
    entry = build(App).serialize()["presenters"]["ctrl"]

    assert entry == {"step": 7.5, "timeout": 2.0}


def test_a_component_serializing_nothing_keeps_the_entry_it_loaded(
    build: Callable[..., AppContainer],
) -> None:
    session = build(App)
    session.quiet.gain = 8.0

    assert session.serialize()["presenters"]["quiet"] == {"gain": 3.0}


def test_an_entry_the_constructor_would_refuse_is_dropped_whole(
    build: Callable[..., AppContainer], caplog: pytest.LogCaptureFixture
) -> None:
    session = build(App)

    with caplog.at_level(logging.WARNING, logger="redsun"):
        written = session.serialize()

    assert written["presenters"]["renamed"] == {"step": 4.0}
    assert "'renamed' tried to save stepsize, which Renamed does not accept" in (
        caplog.text
    )


def test_a_constructor_taking_kwargs_accepts_every_key(
    build: Callable[..., AppContainer],
) -> None:
    entry = build(App).serialize()["presenters"]["anything"]

    assert entry == {"whatever": 1}


def test_a_session_nobody_has_touched_has_no_changes(
    build: Callable[..., AppContainer],
) -> None:
    assert not build(App).has_changes()


def test_a_component_asking_to_be_written_differently_is_a_change(
    build: Callable[..., AppContainer],
) -> None:
    session = build(App)
    session.ctrl.step = 9.0

    assert session.has_changes()


def test_a_value_changed_and_changed_back_reads_as_unchanged(
    build: Callable[..., AppContainer],
) -> None:
    session = build(App)
    session.ctrl.step = 9.0
    session.ctrl.step = 7.5

    assert not session.has_changes()


def test_a_component_that_serializes_nothing_never_changes(
    build: Callable[..., AppContainer],
) -> None:
    session = build(App)
    session.quiet.gain = 8.0

    assert not session.has_changes()


def test_a_refused_key_still_counts_as_a_change(
    build: Callable[..., AppContainer],
) -> None:
    session = build(App)
    session.renamed.step = 9.0

    assert session.has_changes()
