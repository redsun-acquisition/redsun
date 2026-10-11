"""Tests for the example session and the `redsun` command that runs it."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from redsun._cli import main
from redsun._manifest import OWN_PLUGIN
from redsun.errors import BuildError
from redsun.examples import ExampleApp, example_config
from redsun.qt import QtHook
from redsun.session._plugins import manifest

if TYPE_CHECKING:
    from pathlib import Path

    from qtpy.QtWidgets import QApplication

    from redsun.testing import BuildSession


@pytest.mark.qt
@pytest.mark.parametrize("style", [None, *sorted(manifest(OWN_PLUGIN).hooks)])
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


@pytest.mark.qt
@pytest.mark.parametrize(
    ("arguments", "styles"),
    [(["--example"], []), (["--example", "napari"], ["NapariStyle"])],
    ids=["platform", "napari"],
)
def test_the_command_runs_the_example_in_the_style_named(
    arguments: list[str], styles: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run the example with the style the command names installed, and with none for no name."""
    ran: list[list[str]] = []

    def record(session: ExampleApp) -> None:
        installed = session.hooks[QtHook.CONFIGURE_APPLICATION]
        ran.append([type(provider).__name__ for provider in installed])
        # as the real `run` ends: with the exit code of the event loop
        raise SystemExit(0)

    monkeypatch.setattr(ExampleApp, "run", record)

    with pytest.raises(SystemExit) as stopped:
        main(arguments)

    assert stopped.value.code == 0
    assert ran == [styles]


def test_an_unknown_example_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    """Refuse an example name that does not exist, listing the ones that do."""
    with pytest.raises(SystemExit) as stopped:
        main(["--example", "no-such-style"])

    assert stopped.value.code == 2
    assert "napari" in capsys.readouterr().err


def test_no_argument_prints_the_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Print the help and succeed when the command is given nothing to do."""
    assert main([]) == 0
    assert "--example" in capsys.readouterr().out


def test_the_example_without_a_qt_binding_names_the_extras(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit with 1 and name the extras to install when the example cannot be imported."""
    monkeypatch.setitem(sys.modules, "redsun.examples", None)

    assert main(["--example"]) == 1
    assert "redsun[pyqt]" in capsys.readouterr().err


@pytest.mark.qt
def test_a_build_that_fails_is_reported_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit with 1 and print the reason when the example's session cannot be built."""

    def refuse(session: ExampleApp) -> None:
        raise BuildError("A strict session skipped hooks: SomeStyle")

    monkeypatch.setattr(ExampleApp, "run", refuse)

    assert main(["--example"]) == 1
    assert "skipped hooks: SomeStyle" in capsys.readouterr().err
