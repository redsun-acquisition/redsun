"""Config-driven component discovery in the experimental container."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, ClassVar

import pytest
import yaml
from mock_bundle.devices import MockStage
from mock_bundle.keys import Calibration
from mock_bundle.presenters import MockMotorPresenter, MockRegistrar
from mock_bundle.views import MockMotorView

from redsun.experimental import (
    AsPresenter,
    AsView,
    Declare,
    PluginError,
    Session,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from .conftest import BuildSession

SESSION = "mock_session.yaml"


class ConfiguredApp(Session):
    """Every component comes from the file; the class declares none."""


class HeadlessApp(Session):
    """A class of its own, named against a configuration that fills it out."""

    motor_widget: Annotated[AsView[MockMotorView], Declare(title="from-class")]


class PartlyDeclaredApp(Session):
    """One component is annotated, so `wire` can reach it with a type."""

    motor_ctrl: AsPresenter[MockMotorPresenter]
    motor_widget: Annotated[AsView[MockMotorView], Declare(title="from-class")]


DECLARED = {"stage", "motor_ctrl", "late_ctrl", "motor_widget"}


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
    assert stage.axis == "Z"
    assert configured.declarations["motor_ctrl"].instance.step == 4.0
    assert configured.declarations["motor_widget"].instance.title == "from-config"


def test_plugin_provider_supplies_a_dependency(configured: ConfiguredApp) -> None:
    """The bundle's own shared services are loaded from the manifest."""
    presenter = configured.declarations["motor_ctrl"].instance

    assert presenter.calibration == pytest.approx(Calibration(1.2))


def test_shared_value_crosses_from_presenter_to_view(configured: ConfiguredApp) -> None:
    """`provides` works for components the class never named."""
    widget = configured.declarations["motor_widget"].instance

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


def test_configured_component_reads_the_live_registry(
    mock_plugin: None, config_path: Path, build: BuildSession
) -> None:
    class WithRegistrar(Session):
        registrar: AsPresenter[MockRegistrar]

    app = build(WithRegistrar, str(config_path / SESSION))

    assert app.declarations["late_ctrl"].instance.seen == {"registrar": app.registrar}


@pytest.mark.parametrize(
    ("entry", "match"),
    [
        ({"plugin_name": "absent-pkg", "plugin_id": "x"}, "is not installed"),
        ({"plugin_name": "mock-bundle", "plugin_id": "absent"}, "declares no"),
    ],
)
def test_unresolvable_entries_are_reported(
    mock_plugin: None, entry: dict[str, str], match: str, tmp_path: Path
) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump({"presenters": {"ctrl": entry}}))

    class BrokenApp(Session):
        config: ClassVar[str] = str(path)

    with pytest.raises(PluginError, match=match):
        BrokenApp().build()


def test_entry_without_plugin_metadata_is_not_a_component(
    mock_plugin: None, tmp_path: Path, build: BuildSession
) -> None:
    path = tmp_path / "plain.yaml"
    path.write_text(yaml.safe_dump({"presenters": {"ctrl": {"step": 2.0}}}))

    class PlainApp(Session):
        config: ClassVar[str] = str(path)

    assert dict(build(PlainApp).declarations) == {}


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

    assert app.declarations["motor_ctrl"].instance.step == 7.0


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


def test_an_unknown_frontend_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "curses.yaml"
    path.write_text(yaml.safe_dump({"frontend": "curses"}))

    with pytest.raises(ValueError, match="no session is built against"):
        Session.from_config(str(path))


def test_a_frontend_the_container_cannot_serve_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "qt.yaml"
    path.write_text(yaml.safe_dump({"frontend": "pyqt"}))

    with pytest.raises(TypeError, match="which is not one of those"):
        HeadlessApp.from_config(str(path))
