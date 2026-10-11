"""Tests for the example session and the `redsun` command that runs it."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from redsun._cli import main, styles
from redsun.errors import BuildError, HookError
from redsun.examples import ExampleApp, example_config
from redsun.examples._devices import Axis, Plans
from redsun.qt import QtHook

if TYPE_CHECKING:
    from pathlib import Path

    from qtpy.QtWidgets import QApplication

    from redsun.testing import BuildSession

WITHOUT_QT = """
import sys

sys.modules["qtpy"] = None
from redsun._cli import main

sys.exit(main([]))
"""


@pytest.mark.qt
@pytest.mark.parametrize("style", [None, *styles()])
def test_the_example_builds_every_component_under_each_style(
    style: str | None,
    qapp: QApplication,
    build: BuildSession,
    tmp_path: Path,
    unstyled: None,
) -> None:
    """Build the example whole and with every port connected, with the style named installed."""
    config = {**example_config(style), "storage": {"base_dir": str(tmp_path)}}

    session = build(ExampleApp, config)

    installed = session.hooks[QtHook.CONFIGURE_APPLICATION]
    assert len(installed) == (0 if style is None else 1)
    assert not session.unconnected
    assert list(session.acquisition.plans) == ["walk"]


def test_the_plan_locks_its_motor_and_pauses_after_each_move() -> None:
    """Lock the motor for the whole walk and pause after each move, so a run lasts long enough to pause or stop."""
    walk = Plans("plans").walk(Axis(name="focus"), steps=2)

    commands = [message.command for message in walk]

    assert commands[0] == "lock"
    assert commands.count("set") == 2
    assert commands.count("sleep") == 2
    assert commands[-1] == "unlock"


@pytest.mark.qt
@pytest.mark.parametrize(
    ("arguments", "installed"),
    [(["--example"], []), (["--example", "napari"], ["NapariStyle"])],
    ids=["platform", "napari"],
)
def test_the_command_runs_the_example_in_the_style_named(
    arguments: list[str], installed: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run the example with the style the command names installed, and with none for no name."""
    ran: list[list[str]] = []

    def record(session: ExampleApp) -> None:
        providers = session.hooks[QtHook.CONFIGURE_APPLICATION]
        ran.append([type(provider).__name__ for provider in providers])
        # as the real `run` ends: with the exit code of the event loop
        raise SystemExit(0)

    monkeypatch.setattr(ExampleApp, "run", record)

    with pytest.raises(SystemExit) as stopped:
        main(arguments)

    assert stopped.value.code == 0
    assert ran == [installed]


def test_an_unknown_style_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    """Refuse a style that does not exist, listing the ones that do."""
    with pytest.raises(SystemExit) as stopped:
        main(["--example", "no-such-style"])

    assert stopped.value.code == 2
    assert "no style named 'no-such-style'; choose from napari" in (
        capsys.readouterr().err
    )


def test_no_argument_prints_the_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Print the help and succeed when the command is given nothing to do."""
    assert main([]) == 0
    assert "--example" in capsys.readouterr().out


def test_the_command_loads_without_a_qt_binding() -> None:
    """Import the command and print its help in a process where no Qt binding can be imported."""
    done = subprocess.run(
        [sys.executable, "-c", WITHOUT_QT], capture_output=True, text=True, check=False
    )

    assert done.returncode == 0, done.stderr
    assert "--example" in done.stdout


def test_the_example_without_a_qt_binding_names_the_extras(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit with 1 and name the extras to install when the example cannot be imported."""
    monkeypatch.setitem(sys.modules, "redsun.examples", None)

    assert main(["--example"]) == 1
    assert "redsun[pyqt]" in capsys.readouterr().err


@pytest.mark.qt
@pytest.mark.parametrize(
    "error",
    [
        BuildError("a strict session skipped a hook"),
        HookError("a provider does not implement the point"),
        OSError("the log folder cannot be created"),
    ],
    ids=["build", "hook", "folder"],
)
def test_a_session_that_cannot_start_is_reported_without_a_traceback(
    error: Exception,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit with 1 and print the reason when the example's session cannot be built."""

    def refuse(session: ExampleApp) -> None:
        raise error

    monkeypatch.setattr(ExampleApp, "run", refuse)

    assert main(["--example"]) == 1
    assert str(error) in capsys.readouterr().err
