"""Tests for the example session and the `redsun` command that runs it."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import EntryPoint
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

import pytest
from qtpy import API
from qtpy.QtWidgets import QTabWidget
from typer.testing import CliRunner

from redsun import __version__
from redsun._cli import app, styles
from redsun._reports import CheckReport
from redsun.errors import BuildError, HookError
from redsun.examples import ExampleApp, example_config
from redsun.examples._devices import Axis, Plans
from redsun.qt import QtHook, QtSession
from redsun.qt.styles import qlementine

if TYPE_CHECKING:
    from collections.abc import Generator

    from qtpy.QtWidgets import QApplication

    from redsun.testing import BuildSession

needs_qlementine = pytest.mark.skipif(
    find_spec(qlementine.MODULES[API]) is None,
    reason=f"needs the {qlementine.EXTRAS[API]} dependency group",
)

STYLES = [
    pytest.param(name, marks=needs_qlementine) if name == "qlementine" else name
    for name in styles()
]

WITHOUT_QT = """
import sys

sys.modules["qtpy"] = None
from redsun._cli import app

app([])
"""

WIDE = {"COLUMNS": "200"}

MOCK_BUNDLE = Path(__file__).parent / "launchable" / "mock_bundle"

CONFIGS = Path(__file__).parent / "configs"

runner = CliRunner()


@pytest.fixture
def a_plugin_with_services_only(tmp_path: Path) -> Generator[None, None, None]:
    """Present a plugin whose manifest lists a service and no component."""
    (tmp_path / "redsun.yaml").write_text(
        "services:\n  ioc:\n    module: mock_pkg.service.stand_in\n"
    )
    entry = mock.Mock(spec=EntryPoint)
    entry.name = "services-only"
    entry.value = "redsun.yaml"
    entry.dist = None
    with (
        mock.patch("redsun._manifest.entry_points", return_value=[entry]),
        mock.patch("redsun._manifest.files", side_effect=lambda _: tmp_path),
    ):
        yield


@pytest.mark.qt
@pytest.mark.parametrize("style", [None, *STYLES])
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
    assert {box: set(rows) for box, rows in session.positioner.axes.items()} == {
        "stage": {"x", "y"},
        "focus": {"focus"},
    }


@pytest.mark.qt
def test_the_example_shows_its_logs_as_a_tab_of_the_centre(
    qapp: QApplication, build: BuildSession, tmp_path: Path
) -> None:
    """Put the log view in the centre of the window as a tab, and dock the other views."""
    session = build(ExampleApp, {"storage": {"base_dir": str(tmp_path)}})

    centre = session.main_window.centralWidget()

    assert isinstance(centre, QTabWidget)
    assert [centre.tabText(index) for index in range(centre.count())] == ["logs"]


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
    [(["example"], []), (["example", "napari"], ["NapariStyle"])],
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

    done = runner.invoke(app, arguments)

    assert done.exit_code == 0
    assert ran == [installed]


def test_an_unknown_style_is_refused() -> None:
    """Refuse a style that does not exist, listing the ones that do."""
    done = runner.invoke(app, ["example", "no-such-style"], env=WIDE)

    assert done.exit_code == 2
    assert "no style named 'no-such-style'; choose from napari, qlementine" in (
        done.output
    )


def test_no_argument_prints_the_help() -> None:
    """Print the help, listing the commands, when the command is given nothing to do."""
    done = runner.invoke(app, [])

    assert done.exit_code == 0
    assert "example" in done.output


def test_the_version_option_prints_the_installed_version() -> None:
    """Print the version of the installed package and succeed."""
    done = runner.invoke(app, ["--version"])

    assert done.exit_code == 0
    assert done.output.strip() == __version__


def test_plugins_reports_what_each_installed_plugin_offers(mock_plugin: None) -> None:
    """Name each installed plugin with its distribution, its version and the entries of its manifest."""
    done = runner.invoke(app, ["plugins", "--json"])

    assert done.exit_code == 0
    report = json.loads(done.output)
    assert report["redsun"] == __version__
    assert report["problems"] == []
    [plugin] = report["plugins"]
    assert plugin["plugin_name"] == "mock-bundle"
    assert plugin["distribution"] == "mock-bundle-dist"
    assert plugin["version"] == "1.2.3"
    assert {
        "group": "devices",
        "plugin_id": "mock-stage",
        "class": "mock_bundle.devices:MockStage",
    } in plugin["entries"]
    assert {
        "group": "services",
        "plugin_id": "stand-in",
        "module": "mock_pkg.service.stand_in",
    } in plugin["entries"]


def test_plugins_reports_a_skipped_manifest_beside_the_ones_that_loaded(
    a_bad_plugin_beside_a_good_one: None,
) -> None:
    """Report a plugin whose manifest is invalid as a problem, and still list the others."""
    done = runner.invoke(app, ["plugins", "--json"])

    assert done.exit_code == 0
    report = json.loads(done.output)
    assert [plugin["plugin_name"] for plugin in report["plugins"]] == ["mock-bundle"]
    [problem] = report["problems"]
    assert problem["kind"] == "manifest"
    assert problem["where"] == "bad-bundle"
    assert "widgets: Extra inputs are not permitted" in problem["message"]


def test_plugins_lists_a_skipped_plugin_last_in_plain_text(
    a_bad_plugin_beside_a_good_one: None,
) -> None:
    """Print a plugin of unknown distribution by its name alone, and a skipped one under its own heading."""
    done = runner.invoke(app, ["plugins"])

    assert done.exit_code == 0
    listed, _, skipped = done.output.partition("Skipped:")
    assert listed.startswith("mock-bundle\n")
    assert "bad-bundle: manifest" in skipped


def test_plugins_lists_a_plugin_whose_distribution_cannot_be_read() -> None:
    """List a plugin without its distribution when the metadata of that distribution cannot be read."""
    entry = mock.Mock(spec=EntryPoint)
    entry.name = "mock-bundle"
    entry.value = "redsun.yaml"
    entry.dist = mock.Mock()
    type(entry.dist).name = mock.PropertyMock(side_effect=KeyError("Name"))

    with (
        mock.patch("redsun._manifest.entry_points", return_value=[entry]),
        mock.patch("redsun._manifest.files", return_value=MOCK_BUNDLE),
    ):
        done = runner.invoke(app, ["plugins"])

    assert done.exit_code == 0
    assert done.output.startswith("mock-bundle\n")


def test_plugins_lists_the_ids_of_each_group_in_plain_text(mock_plugin: None) -> None:
    """Print each plugin with its distribution and version, and its ids by group."""
    done = runner.invoke(app, ["plugins"])

    assert done.exit_code == 0
    assert "mock-bundle (mock-bundle-dist 1.2.3)" in done.output
    assert "presenters: described, limited, mock-late, mock-motor" in done.output


def test_the_command_loads_without_a_qt_binding() -> None:
    """Import the command and print its help in a process where no Qt binding can be imported."""
    done = subprocess.run(
        [sys.executable, "-c", WITHOUT_QT], capture_output=True, text=True, check=False
    )

    assert done.returncode == 0, done.stderr
    assert "example" in done.stdout


def test_the_example_without_a_qt_binding_names_the_extras(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exit with 1 and name the extras to install when the example cannot be imported."""
    monkeypatch.setitem(sys.modules, "redsun.examples", None)

    done = runner.invoke(app, ["example"])

    assert done.exit_code == 1
    assert "redsun[pyqt]" in done.output


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
) -> None:
    """Exit with 1 and print the reason when the example's session cannot be built."""

    def refuse(session: ExampleApp) -> None:
        raise error

    monkeypatch.setattr(ExampleApp, "run", refuse)

    done = runner.invoke(app, ["example"])

    assert done.exit_code == 1
    assert str(error) in done.output


@pytest.mark.qt
def test_run_starts_the_session_the_files_describe(
    mock_plugin: None,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Merge the files in order, add `--mock` and `--strict`, and start the Qt session they name."""
    layer = tmp_path / "layer.yaml"
    layer.write_text(
        "devices:\n  stage:\n    plugin_name: mock-bundle\n"
        "    plugin_id: mock-stage\n    axis: Y\n"
    )
    started: list[dict[str, object]] = []

    def record(session: QtSession) -> None:
        started.append(session.serialize())
        # as the real `run` ends: with the exit code of the event loop
        raise SystemExit(0)

    monkeypatch.setattr(QtSession, "run", record)

    done = runner.invoke(
        app,
        ["run", str(CONFIGS / "mock_session.yaml"), str(layer), "--mock", "--strict"],
    )

    assert done.exit_code == 0, done.output
    [config] = started
    assert config["devices"]["stage"]["axis"] == "Y"  # type: ignore[index]
    assert config["mock"] is True
    assert config["strict"] is True


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (None, "could not start. [Errno 2] No such file or directory"),
        ("session: s\nfrontend: nowhere\n", "frontend 'nowhere'"),
        ("session: s\n", "names no frontend, so it has nothing to show. Name one"),
    ],
    ids=["missing file", "unknown frontend", "no frontend"],
)
def test_run_refuses_a_session_it_cannot_start(
    content: str | None, reason: str, tmp_path: Path
) -> None:
    """Exit with 1 and say why for a missing file, an unknown frontend and a file naming no frontend."""
    path = tmp_path / "session.yaml"
    if content is not None:
        path.write_text(content)

    done = runner.invoke(app, ["run", str(path)], env=WIDE)

    assert done.exit_code == 1
    assert reason in done.output


@pytest.mark.qt
def test_run_reports_a_session_that_fails_to_build(
    mock_plugin: None, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit with 1 and print the reason when the session raises while it starts."""

    def refuse(session: QtSession) -> None:
        raise BuildError("a strict session skipped a component")

    monkeypatch.setattr(QtSession, "run", refuse)

    done = runner.invoke(app, ["run", str(CONFIGS / "mock_session.yaml")])

    assert done.exit_code == 1
    assert "a strict session skipped a component" in done.output


def test_check_prints_the_report_as_json(mock_plugin: None, tmp_path: Path) -> None:
    """Print the check's report as JSON, and exit with 1 when a record failed."""
    session = tmp_path / "session.yaml"
    session.write_text(
        "session: s\npresenters:\n  ghost:\n    plugin_name: nope\n    plugin_id: x\n"
    )

    done = runner.invoke(app, ["check", str(session), "--json"])

    assert done.exit_code == 1
    report = CheckReport.model_validate_json(done.output)
    assert [(c.name, c.status) for c in report.components] == [("ghost", "failed")]


def test_check_exits_with_0_when_only_undecided(
    mock_plugin: None, tmp_path: Path
) -> None:
    """Exit with 0 when nothing failed, listing what could not be decided."""
    session = tmp_path / "session.yaml"
    session.write_text(
        "session: s\npresenters:\n  m:\n    plugin_name: mock-bundle\n"
        "    plugin_id: mock-motor\nviews:\n  v:\n    plugin_name: mock-bundle\n"
        "    plugin_id: mock-motor-view\nwiring:\n  m.sig_unknown: v.refresh\n"
    )

    done = runner.invoke(app, ["check", str(session)])

    assert done.exit_code == 0
    assert "undecided  wiring     m.sig_unknown -> v.refresh" in done.output
    assert "not checked:" in done.output


@pytest.mark.qt
def test_run_reports_a_type_error_from_the_file_without_a_traceback(
    mock_plugin: None, qapp: QApplication, tmp_path: Path
) -> None:
    """Exit with 1 and the reason when the file declares a stack half twice."""
    session = tmp_path / "session.yaml"
    session.write_text(
        "session: s\nfrontend: qt\npresenters:\n  motor_view:\n"
        "    plugin_name: mock-bundle\n    plugin_id: mock-late\n"
        "stacks:\n  motor:\n    plugin_name: mock-bundle\n    plugin_id: mock-motor\n"
    )

    done = runner.invoke(app, ["run", str(session)])

    assert done.exit_code == 1
    assert "already" in done.output
    assert isinstance(done.exception, SystemExit)


def test_describe_prints_one_entry_as_json(mock_plugin: None) -> None:
    """Print the report of one entry as JSON, and exit with 0 when nothing is wrong."""
    done = runner.invoke(app, ["describe", "mock-bundle", "mock-motor", "--json"])

    assert done.exit_code == 0, done.output
    report = json.loads(done.output)
    assert [c["plugin_id"] for c in report["components"]] == ["mock-motor"]


def test_describe_exits_1_on_a_problem(mock_plugin: None) -> None:
    """Exit with 1 and name the parameter at fault when a component has a problem."""
    done = runner.invoke(app, ["describe", "mock-bundle", "described"], env=WIDE)

    assert done.exit_code == 1
    assert "described.scale" in done.output


def test_describe_of_a_plugin_without_components_exits_0(
    a_plugin_with_services_only: None,
) -> None:
    """Describe nothing and exit with 0 for a plugin that lists no component."""
    done = runner.invoke(app, ["describe", "services-only", "--json"])

    assert done.exit_code == 0, done.output
    assert json.loads(done.output)["components"] == []
