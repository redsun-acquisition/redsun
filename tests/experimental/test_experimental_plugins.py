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
    AppContainer,
    AsPresenter,
    AsView,
    Declare,
    PluginError,
)

if TYPE_CHECKING:
    from pathlib import Path


class ConfiguredApp(AppContainer):
    """Every component comes from the file; the class declares none."""

    __slots__ = ()


class HeadlessApp(AppContainer):
    """A class of its own, named against a configuration that fills it out."""

    __slots__ = ()

    motor_widget: Annotated[AsView[MockMotorView], Declare(title="from-class")]


class PartlyDeclaredApp(AppContainer):
    """One component is annotated, so `wire` can reach it with a type."""

    __slots__ = ()

    motor_ctrl: AsPresenter[MockMotorPresenter]
    motor_widget: Annotated[AsView[MockMotorView], Declare(title="from-class")]


def _build(cls: type[AppContainer], path: Path) -> AppContainer:
    return cls(str(path / "mock_session.yaml")).build()


def test_components_come_up_from_the_file_alone(
    mock_plugin: None, config_path: Path
) -> None:
    """A class declaring nothing still builds the whole configured session."""
    app = _build(ConfiguredApp, config_path)
    try:
        names = set(app.declarations)
        assert names == {"stage", "motor_ctrl", "late_ctrl", "motor_widget"}
        assert isinstance(app.declarations["motor_ctrl"].instance, MockMotorPresenter)
        assert isinstance(app.declarations["motor_widget"].instance, MockMotorView)
        assert isinstance(app.devices["stage"], MockStage)
    finally:
        app.shutdown()


def test_config_kwargs_reach_the_constructor(
    mock_plugin: None, config_path: Path
) -> None:
    """Plugin metadata is stripped; everything else is a keyword argument."""
    app = _build(ConfiguredApp, config_path)
    try:
        stage = app.devices["stage"]
        assert isinstance(stage, MockStage)
        assert stage.axis == "Z"
        assert app.declarations["motor_ctrl"].instance.step == 4.0
        assert app.declarations["motor_widget"].instance.title == "from-config"
    finally:
        app.shutdown()


def test_plugin_provider_supplies_a_dependency(
    mock_plugin: None, config_path: Path
) -> None:
    """The bundle's own dishka provider is loaded from the manifest."""
    app = _build(ConfiguredApp, config_path)
    try:
        presenter = app.declarations["motor_ctrl"].instance
        assert presenter.calibration == pytest.approx(Calibration(1.2))
    finally:
        app.shutdown()


def test_shared_value_crosses_from_presenter_to_view(
    mock_plugin: None, config_path: Path
) -> None:
    """`provides` works for components the class never named."""
    app = _build(ConfiguredApp, config_path)
    try:
        widget = app.declarations["motor_widget"].instance
        assert widget.readings == {"stage": pytest.approx(4.8)}
        assert widget.missing is None
    finally:
        app.shutdown()


def test_wiring_section_is_applied(mock_plugin: None, config_path: Path) -> None:
    """Ports named as strings connect once every component exists."""
    app = _build(ConfiguredApp, config_path)
    try:
        links = app.virtual_container.connections
        assert [
            (c.publisher, c.publisher_port, c.consumer, c.consumer_port) for c in links
        ] == [("motor_ctrl", "sig_moved", "motor_widget", "refresh")]
    finally:
        app.shutdown()


def test_annotation_and_config_describe_one_component(
    mock_plugin: None, config_path: Path
) -> None:
    """A class-body declaration wins over the file, and is typed."""
    app = _build(PartlyDeclaredApp, config_path)
    try:
        assert app.motor_widget.title == "from-class"
        assert app.motor_ctrl.step == 4.0
        assert set(app.declarations) == {
            "stage",
            "motor_ctrl",
            "late_ctrl",
            "motor_widget",
        }
    finally:
        app.shutdown()


def test_configured_component_reads_the_live_registry(
    mock_plugin: None, config_path: Path
) -> None:
    """A component discovered from the file sees what one declared in the class did."""

    class WithRegistrar(AppContainer):
        __slots__ = ()
        registrar: AsPresenter[MockRegistrar]

    app = WithRegistrar(str(config_path / "mock_session.yaml")).build()
    try:
        assert app.declarations["late_ctrl"].instance.seen == {
            "registrar": app.registrar
        }
    finally:
        app.shutdown()


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
    """A named component that cannot be found fails the build, loudly."""
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump({"presenters": {"ctrl": entry}}))

    class BrokenApp(AppContainer):
        __slots__ = ()
        config: ClassVar[str] = str(path)

    with pytest.raises(PluginError, match=match):
        BrokenApp().build()


def test_entry_without_plugin_metadata_is_not_a_component(
    mock_plugin: None, tmp_path: Path
) -> None:
    """A section entry that names no plugin configures nothing by itself."""
    path = tmp_path / "plain.yaml"
    path.write_text(yaml.safe_dump({"presenters": {"ctrl": {"step": 2.0}}}))

    class PlainApp(AppContainer):
        __slots__ = ()
        config: ClassVar[str] = str(path)

    app = PlainApp().build()
    try:
        assert dict(app.declarations) == {}
    finally:
        app.shutdown()


def test_a_session_needs_no_container_class(
    mock_plugin: None, config_path: Path
) -> None:
    """The file alone names the components, and comes back unbuilt."""
    app = AppContainer.from_config(str(config_path / "mock_headless.yaml"))
    assert not app.is_built
    app.build()
    try:
        assert set(app.declarations) == {
            "stage",
            "motor_ctrl",
            "late_ctrl",
            "motor_widget",
        }
        assert app.virtual_container.session == "mock-session"
    finally:
        app.shutdown()


def test_from_config_takes_the_configuration_itself(mock_plugin: None) -> None:
    """A mapping is a session as much as a path to one is."""
    app = AppContainer.from_config(
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
    ).build()
    try:
        assert app.declarations["motor_ctrl"].instance.step == 7.0
    finally:
        app.shutdown()


def test_the_class_keeps_what_it_declares(mock_plugin: None, config_path: Path) -> None:
    """Calling it on a subclass builds that subclass, declarations and all."""
    app = HeadlessApp.from_config(str(config_path / "mock_headless.yaml")).build()
    try:
        assert isinstance(app, HeadlessApp)
        assert app.motor_widget.title == "from-class"
    finally:
        app.shutdown()


def test_the_configuration_is_the_instance_alone(
    mock_plugin: None, config_path: Path
) -> None:
    """Naming a session leaves the class it was named on untouched."""
    app = AppContainer.from_config(str(config_path / "mock_headless.yaml"))
    assert AppContainer.config is None
    assert set(app.build().declarations)
    app.shutdown()


def test_an_unknown_frontend_is_refused(tmp_path: Path) -> None:
    """A toolkit no container is built against fails before anything is built."""
    path = tmp_path / "curses.yaml"
    path.write_text(yaml.safe_dump({"frontend": "curses"}))

    with pytest.raises(ValueError, match="no container is built against"):
        AppContainer.from_config(str(path))


def test_a_frontend_the_container_cannot_serve_is_refused(tmp_path: Path) -> None:
    """A class already built against another toolkit is not quietly replaced."""
    path = tmp_path / "qt.yaml"
    path.write_text(yaml.safe_dump({"frontend": "pyqt"}))

    with pytest.raises(TypeError, match="which is not one of those"):
        HeadlessApp.from_config(str(path))
