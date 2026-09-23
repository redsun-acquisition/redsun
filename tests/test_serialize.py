"""Tests for a session writing back out the configuration that rebuilds it."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
import yaml
from ophyd_async.core import StandardReadable, StandardReadableFormat, soft_signal_rw

from redsun import (
    AsDevice,
    AsPresenter,
    ConfigurationInUse,
    Session,
)
from redsun.aio import run_coro

if TYPE_CHECKING:
    from pathlib import Path

    from .conftest import BuildSession


class Stage(StandardReadable):
    """Device writing back the axis its configuration signal holds."""

    def __init__(self, name: str, axis: str = "X") -> None:
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.axis = soft_signal_rw(str, initial_value=axis)
        super().__init__(name=name)

    def serialize(self) -> dict[str, str]:
        return {"axis": run_coro(self.axis.get_value())}


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

    def __init__(self, name: str, *, gain: float = 1.0) -> None:
        self.name = name
        self.gain = gain


class Renamed:
    """Presenter asking to save a key its own constructor would refuse."""

    def __init__(self, name: str, *, step: float = 1.0) -> None:
        self.name = name
        self.step = step

    def serialize(self) -> dict[str, float]:
        return {"stepsize": self.step}


class Anything:
    """Presenter whose constructor accepts every key, through ``**kwargs``."""

    def __init__(self, name: str, **kwargs: object) -> None:
        self.name = name
        self.kwargs = kwargs

    def serialize(self) -> dict[str, int]:
        return {"whatever": 1}


class App(Session):
    config: ClassVar[dict[str, Any]] = {
        "schema_version": 1.0,
        "session": "round-trip",
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
    build: BuildSession,
) -> None:
    session = build(App)
    session.ctrl.step = 9.0

    async def set_axis_to_y() -> None:
        await session.stage.axis.set("Y")

    run_coro(set_axis_to_y())
    written = session.serialize()
    session.shutdown()

    rebuilt = build(App, written)

    assert rebuilt.ctrl.step == 9.0
    assert run_coro(rebuilt.stage.axis.get_value()) == "Y"
    assert rebuilt.serialize() == written


def test_serialize_writes_a_parameter_no_source_named(
    build: BuildSession,
) -> None:
    entry = build(App).serialize()["presenters"]["ctrl"]

    assert entry == {"step": 7.5, "timeout": 2.0}


def test_a_component_serializing_nothing_keeps_the_entry_it_loaded(
    build: BuildSession,
) -> None:
    session = build(App)
    session.quiet.gain = 8.0

    assert session.serialize()["presenters"]["quiet"] == {"gain": 3.0}


def test_an_entry_the_constructor_would_refuse_is_dropped_whole(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    session = build(App)

    with caplog.at_level(logging.WARNING, logger="redsun"):
        written = session.serialize()

    assert written["presenters"]["renamed"] == {"step": 4.0}
    assert "'renamed' tried to save stepsize, which Renamed does not accept" in (
        caplog.text
    )


def test_a_constructor_taking_kwargs_accepts_every_key(
    build: BuildSession,
) -> None:
    entry = build(App).serialize()["presenters"]["anything"]

    assert entry == {"whatever": 1}


def test_a_session_nobody_has_touched_has_no_changes(
    build: BuildSession,
) -> None:
    assert not build(App).has_changes()


def test_a_component_asking_to_be_written_differently_is_a_change(
    build: BuildSession,
) -> None:
    session = build(App)
    session.ctrl.step = 9.0

    assert session.has_changes()


def test_a_value_changed_and_changed_back_reads_as_unchanged(
    build: BuildSession,
) -> None:
    session = build(App)
    session.ctrl.step = 9.0
    session.ctrl.step = 7.5

    assert not session.has_changes()


def test_a_component_that_serializes_nothing_never_changes(
    build: BuildSession,
) -> None:
    session = build(App)
    session.quiet.gain = 8.0

    assert not session.has_changes()


def test_a_refused_key_still_counts_as_a_change(
    build: BuildSession,
) -> None:
    session = build(App)
    session.renamed.step = 9.0

    assert session.has_changes()


def test_a_written_session_comes_back_from_the_file(
    tmp_path: Path, build: BuildSession
) -> None:
    session = build(App)
    session.ctrl.step = 9.0
    written = session.write(tmp_path / "session.yaml")
    session.shutdown()

    rebuilt = build(App, str(written))

    assert rebuilt.ctrl.step == 9.0
    assert yaml.safe_load(written.read_text()) == session.serialize()


def test_the_written_file_is_one_flat_session(
    tmp_path: Path, build: BuildSession
) -> None:
    """A session layered from several sources writes what the merge produced."""
    base = tmp_path / "instrument.yaml"
    base.write_text(yaml.safe_dump({"presenters": {"ctrl": {"step": 1.5}}}))

    written = build(App, [str(base), {"session": "layered"}]).write(
        tmp_path / "out.yaml"
    )

    assert yaml.safe_load(written.read_text())["session"] == "layered"
    assert yaml.safe_load(written.read_text())["presenters"]["ctrl"]["step"] == 1.5


def test_the_written_file_keeps_the_transport(
    tmp_path: Path, build: BuildSession
) -> None:
    """The key names no service, and is still what the file says they speak."""
    source = {"services": {"transport": "pv-access", "beamline": {"prefix": "BL:"}}}

    written = build(App, source).write(tmp_path / "out.yaml")
    rebuilt = build(App, str(written))

    assert yaml.safe_load(written.read_text())["services"]["transport"] == "pv-access"
    assert rebuilt.transport == "pv-access"
    assert rebuilt.services["beamline"].transport == "pv-access"


def test_writing_over_a_source_is_refused(tmp_path: Path, build: BuildSession) -> None:
    """Overwriting one replaces what every session sharing it reads."""
    source = tmp_path / "shared.yaml"
    source.write_text(yaml.safe_dump({"session": "shared"}))
    session = build(App, str(source))

    with pytest.raises(ConfigurationInUse, match="shared.yaml"):
        session.write(tmp_path / ".." / source.parent.name / "shared.yaml")

    assert yaml.safe_load(source.read_text()) == {"session": "shared"}
