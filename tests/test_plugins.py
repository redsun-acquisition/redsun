"""Config-driven component discovery in a session."""

from __future__ import annotations

import re
from importlib.metadata import EntryPoint
from typing import TYPE_CHECKING, Annotated, ClassVar, TypeVar
from unittest import mock

import pytest
import yaml
from mock_bundle.devices import MockStage
from mock_bundle.keys import Calibration
from mock_bundle.presenters import (
    MockLatePresenter,
    MockMotorPresenter,
    MockRegistrar,
)
from mock_bundle.views import MockMotorView

from redsun import (
    AsPresenter,
    AsView,
    ConfigurationError,
    Declare,
    Session,
    SessionConfig,
    _manifest,
)
from redsun.aio import run_coro
from redsun.qt import QtSession

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from .conftest import BuildSession

SESSION = "mock_session.yaml"


class ConfiguredApp(Session):
    """Every component comes from the file; the class declares none."""


class CustomSession(Session):
    """A session a third-party package registers as a frontend."""


class FrontendReader:
    """A presenter recording the frontend its session reports."""

    def __init__(self, name: str, config: SessionConfig) -> None:
        self.name = name
        self.frontend = config.frontend


class HeadlessApp(Session):
    """A class of its own, named against a configuration that fills it out."""

    motor_widget: Annotated[AsView[MockMotorView], Declare(title="from-class")]


class PartlyDeclaredApp(Session):
    """One component is annotated, so `wire` can reach it with a type."""

    motor_ctrl: AsPresenter[MockMotorPresenter]
    motor_widget: Annotated[AsView[MockMotorView], Declare(title="from-class")]


DECLARED = {"stage", "motor_ctrl", "late_ctrl", "motor_widget"}

C = TypeVar("C")


def built(session: Session, name: str, kind: type[C]) -> C:
    """Return the component *session* built under *name*, checked to be a *kind*."""
    instance = session.declarations[name].instance
    assert isinstance(instance, kind), (
        f"{name!r} is {instance!r}, not a {kind.__name__}"
    )
    return instance


@pytest.fixture
def configured(
    mock_plugin: None, config_path: Path, build: Callable[..., ConfiguredApp]
) -> ConfiguredApp:
    """Return the session ``mock_session.yaml`` describes, built."""
    return build(ConfiguredApp, str(config_path / SESSION))


def test_components_come_up_from_the_file_alone(configured: ConfiguredApp) -> None:
    """A class declaring nothing still builds the whole configured session."""
    assert set(configured.declarations) == DECLARED
    assert isinstance(
        configured.declarations["motor_ctrl"].instance, MockMotorPresenter
    )
    assert isinstance(configured.declarations["motor_widget"].instance, MockMotorView)
    assert isinstance(configured.devices["stage"], MockStage)


def test_config_kwargs_reach_the_constructor(configured: ConfiguredApp) -> None:
    """Plugin metadata is stripped; everything else is a keyword argument."""
    stage = configured.devices["stage"]

    assert isinstance(stage, MockStage)
    assert run_coro(stage.axis.get_value()) == "Z"
    assert built(configured, "motor_ctrl", MockMotorPresenter).step == 4.0
    assert built(configured, "motor_widget", MockMotorView).title == "from-config"


def test_plugin_provider_supplies_a_dependency(configured: ConfiguredApp) -> None:
    """The bundle's own shared services are loaded from the manifest."""
    presenter = built(configured, "motor_ctrl", MockMotorPresenter)

    assert presenter.calibration == pytest.approx(Calibration(1.2))


def test_shared_value_crosses_from_presenter_to_view(configured: ConfiguredApp) -> None:
    """`provides` works for components the class never named."""
    widget = built(configured, "motor_widget", MockMotorView)

    assert widget.readings == {"stage": pytest.approx(4.8)}
    assert widget.missing is None


def test_wiring_section_is_applied(configured: ConfiguredApp) -> None:
    """Ports named as strings connect once every component exists."""
    links = configured.connections

    assert [
        (c.publisher, c.publisher_port, c.consumer, c.consumer_port) for c in links
    ] == [("motor_ctrl", "sig_moved", "motor_widget", "refresh")]


def test_annotation_and_config_describe_one_component(
    mock_plugin: None, config_path: Path, build: BuildSession
) -> None:
    app = build(PartlyDeclaredApp, str(config_path / SESSION))

    assert app.motor_widget.title == "from-class"
    assert app.motor_ctrl.step == 4.0
    assert set(app.declarations) == DECLARED


def test_configured_component_receives_the_catalogue(
    mock_plugin: None, config_path: Path, build: BuildSession
) -> None:
    class WithRegistrar(Session):
        registrar: AsPresenter[MockRegistrar]

    app = build(WithRegistrar, str(config_path / SESSION))

    assert built(app, "late_ctrl", MockLatePresenter).seen == {
        "registrar": app.registrar
    }


@pytest.mark.parametrize(
    ("entry", "match"),
    [
        ({"plugin_name": "absent-pkg", "plugin_id": "x"}, "is not installed"),
        ({"plugin_name": "mock-bundle", "plugin_id": "absent"}, "declares no"),
        ({"step": "2.0"}, "names no plugin"),
    ],
)
def test_an_entry_that_does_not_resolve_is_left_out_with_an_error(
    mock_plugin: None,
    entry: dict[str, str],
    match: str,
    caplog: pytest.LogCaptureFixture,
    build: BuildSession,
) -> None:
    class BrokenApp(Session):
        config: ClassVar[dict[str, object]] = {"presenters": {"ctrl": entry}}

    app = build(BrokenApp)

    assert app.is_built
    assert dict(app.presenters) == {}
    assert re.search(f"Failed to build presenter 'ctrl': .*{match}", caplog.text)


def test_a_session_needs_no_container_class(
    mock_plugin: None, config_path: Path, build: BuildSession
) -> None:
    unbuilt = Session.from_config(str(config_path / "mock_headless.yaml"))
    assert not unbuilt.is_built

    app = build(unbuilt)

    assert set(app.declarations) == DECLARED
    assert app.name == "mock-session"


def test_from_config_takes_the_configuration_itself(
    mock_plugin: None, build: BuildSession
) -> None:
    app = build(
        Session.from_config(
            {
                "session": "lab",
                "presenters": {
                    "motor_ctrl": {
                        "plugin_name": "mock-bundle",
                        "plugin_id": "mock-motor",
                        "step": 7.0,
                    }
                },
                "providers": {
                    "services": {
                        "plugin_name": "mock-bundle",
                        "plugin_id": "mock-services",
                    }
                },
            }
        )
    )

    assert built(app, "motor_ctrl", MockMotorPresenter).step == 7.0


def test_the_class_keeps_what_it_declares(
    mock_plugin: None, config_path: Path, build: BuildSession
) -> None:
    app = build(HeadlessApp.from_config(str(config_path / "mock_headless.yaml")))

    assert isinstance(app, HeadlessApp)
    assert app.motor_widget.title == "from-class"


def test_the_configuration_is_the_instance_alone(
    mock_plugin: None, config_path: Path
) -> None:
    app = Session.from_config(str(config_path / "mock_headless.yaml"))
    assert Session.config is None
    assert set(app.build().declarations)
    app.shutdown()


def test_a_plugin_whose_manifest_is_invalid_is_left_out(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    (tmp_path / "redsun.yaml").write_text("widgets: {}\n")
    entry = mock.Mock(spec=EntryPoint)
    entry.name = "bad-bundle"
    entry.value = "redsun.yaml"

    class BadApp(Session):
        config: ClassVar[dict[str, object]] = {
            "presenters": {"ctrl": {"plugin_name": "bad-bundle", "plugin_id": "x"}}
        }

    with (
        mock.patch("redsun._manifest.entry_points", return_value=[entry]),
        mock.patch("redsun._manifest.files", return_value=tmp_path),
    ):
        app = build(BadApp)

    assert dict(app.presenters) == {}
    assert 'Plugin "bad-bundle" manifest' in caplog.text
    assert "widgets: Extra inputs are not permitted" in caplog.text


def test_from_config_refuses_a_session_that_names_itself_nothing() -> None:
    with pytest.raises(ConfigurationError, match="must name itself"):
        Session.from_config({"presenters": {}})


def test_an_unknown_frontend_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "curses.yaml"
    path.write_text(yaml.safe_dump({"session": "lab", "frontend": "curses"}))

    with pytest.raises(ValueError, match="no session is built against"):
        Session.from_config(str(path))


def test_a_frontend_the_container_cannot_serve_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "qt.yaml"
    path.write_text(yaml.safe_dump({"session": "lab", "frontend": "qt"}))

    with pytest.raises(TypeError, match="which is not one of those"):
        HeadlessApp.from_config(str(path))


def test_a_frontend_another_package_registers_is_built_on() -> None:
    entry = EntryPoint(
        "custom", f"{CustomSession.__module__}:CustomSession", "redsun.frontends"
    )

    with mock.patch("redsun._config.entry_points", return_value=[entry]):
        unbuilt = Session.from_config({"session": "lab", "frontend": "custom"})

    assert type(unbuilt) is CustomSession


@pytest.mark.parametrize(("base", "frontend"), [(Session, None), (QtSession, "qt")])
def test_a_session_reports_the_frontend_it_is_built_on(
    base: type[Session], frontend: str | None, qapp: object, build: BuildSession
) -> None:
    """The file need not say it: the class does."""

    class App(base):  # type: ignore[valid-type,misc]
        reader: AsPresenter[FrontendReader]

    app = build(App, {"session": "lab"})

    assert built(app, "reader", FrontendReader).frontend == frontend


def test_a_build_looks_each_plugin_up_once(
    mock_plugin: None, config_path: Path, build: Callable[..., ConfiguredApp]
) -> None:
    """Five entries name one plugin; a second build looks it up again."""
    lookups = vars(_manifest)["entry_points"]
    assert isinstance(lookups, mock.Mock)

    build(ConfiguredApp, str(config_path / SESSION))
    once = lookups.call_count
    build(ConfiguredApp, str(config_path / SESSION))

    assert (once, lookups.call_count) == (1, 2)


def test_a_session_builds_again_after_shutdown(
    mock_plugin: None, config_path: Path, build: Callable[..., ConfiguredApp]
) -> None:
    """What one component shares reaches another on the second build too."""
    app = build(ConfiguredApp, str(config_path / SESSION))
    app.shutdown()

    app.build()

    widget = built(app, "motor_widget", MockMotorView)
    assert widget.readings == {"stage": pytest.approx(4.8)}
