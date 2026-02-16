"""Tests for the container-based architecture."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from redsun.containers import (
    AppContainer,
    DeviceComponent,
    PresenterComponent,
    ViewComponent,
)


# ── Component wrappers ──────────────────────────────────────────────


class TestComponentWrappers:
    """Tests for DeviceComponent, PresenterComponent, ViewComponent."""

    def test_device_component_pending_repr(self) -> None:
        from mock_pkg.device import MyMotor

        comp = DeviceComponent(
            MyMotor, "m", axis=["X"], step_size={"X": 0.1},
            egu="mm", integer=1, floating=1.0, string="s",
        )
        assert "pending" in repr(comp)

    def test_device_component_build(self) -> None:
        from mock_pkg.device import MyMotor

        comp = DeviceComponent(
            MyMotor, "m", axis=["X"], step_size={"X": 0.1},
            egu="mm", integer=1, floating=1.0, string="s",
        )
        device = comp.build()
        assert device.name == "m"
        assert "built" in repr(comp)

    def test_instance_before_build_raises(self) -> None:
        from mock_pkg.device import MyMotor

        comp = DeviceComponent(
            MyMotor, "m", axis=["X"], step_size={"X": 0.1},
            egu="mm", integer=1, floating=1.0, string="s",
        )
        with pytest.raises(RuntimeError, match="not been instantiated"):
            _ = comp.instance

    def test_presenter_component_build(self) -> None:
        from mock_pkg.controller import MockController

        from sunflare.virtual import VirtualBus

        comp = PresenterComponent(
            MockController, "ctrl",
            string="s", integer=1, floating=0.0, boolean=False,
        )
        bus = VirtualBus()
        presenter = comp.build({}, bus)
        assert presenter is comp.instance
        assert "built" in repr(comp)

    def test_view_component_build(self) -> None:
        from mock_pkg.view import MockQtView

        from qtpy.QtWidgets import QApplication
        from sunflare.virtual import VirtualBus

        _ = QApplication.instance() or QApplication([])
        comp = ViewComponent(MockQtView, "v")
        bus = VirtualBus()
        view = comp.build(bus)
        assert view is comp.instance
        assert "built" in repr(comp)


# ── Metaclass ────────────────────────────────────────────────────────


class TestAppContainerMeta:
    """Tests for metaclass component collection."""

    def test_collects_components(self) -> None:
        from mock_pkg.controller import MockController
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = DeviceComponent(
                MyMotor, "motor", axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )
            ctrl = PresenterComponent(
                MockController, "ctrl",
                string="s", integer=1, floating=0.0, boolean=False,
            )

        assert "motor" in TestApp._device_components
        assert "ctrl" in TestApp._presenter_components
        assert len(TestApp._view_components) == 0

    def test_base_container_has_empty_components(self) -> None:
        assert len(AppContainer._device_components) == 0
        assert len(AppContainer._presenter_components) == 0
        assert len(AppContainer._view_components) == 0

    def test_inherits_components_from_base(self) -> None:
        from mock_pkg.device import MyMotor

        class Base(AppContainer):
            motor = DeviceComponent(
                MyMotor, "motor", axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )

        class Child(Base):
            pass

        assert "motor" in Child._device_components


# ── Build lifecycle ──────────────────────────────────────────────────


class TestAppContainerBuild:
    """Tests for the build lifecycle."""

    def test_build_devices_and_presenters(self) -> None:
        from mock_pkg.controller import MockController
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = DeviceComponent(
                MyMotor, "motor", axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )
            ctrl = PresenterComponent(
                MockController, "ctrl",
                string="s", integer=1, floating=0.0, boolean=False,
            )

        app = TestApp()
        assert not app.is_built

        app.build()
        assert app.is_built
        assert "motor" in app.devices
        assert "ctrl" in app.presenters

    def test_build_idempotent(self) -> None:
        class EmptyApp(AppContainer):
            pass

        app = EmptyApp()
        app.build()
        app.build()  # should warn, not fail
        assert app.is_built

    def test_properties_raise_before_build(self) -> None:
        class EmptyApp(AppContainer):
            pass

        app = EmptyApp()
        with pytest.raises(RuntimeError):
            _ = app.devices
        with pytest.raises(RuntimeError):
            _ = app.presenters
        with pytest.raises(RuntimeError):
            _ = app.views
        with pytest.raises(RuntimeError):
            _ = app.virtual_bus
        with pytest.raises(RuntimeError):
            _ = app.di_container

    def test_config_defaults(self) -> None:
        app = AppContainer()
        assert app.config["session"] == "Redsun"
        assert app.config["frontend"] == "pyqt"

    def test_config_override(self) -> None:
        app = AppContainer(session="MySession", frontend="pyside")
        assert app.config["session"] == "MySession"
        assert app.config["frontend"] == "pyside"

    def test_shutdown(self) -> None:
        class EmptyApp(AppContainer):
            pass

        app = EmptyApp()
        app.build()
        assert app.is_built
        app.shutdown()
        assert not app.is_built

    def test_shutdown_noop_when_not_built(self) -> None:
        app = AppContainer()
        app.shutdown()  # should not raise


# ── from_config ──────────────────────────────────────────────────────


class TestFromConfig:
    """Tests for YAML-based dynamic container creation."""

    def test_from_config_motor(
        self, mock_entry_points: Any, config_path: Path
    ) -> None:
        container = AppContainer.from_config(
            str(config_path / "mock_motor_config.yaml")
        )
        assert not container.is_built
        assert container.config["frontend"] == "pyqt"

        container.build()
        assert len(container.devices) == 2

    def test_from_config_returns_qt_container(
        self, mock_entry_points: Any, config_path: Path
    ) -> None:
        from redsun.containers.qt_container import QtAppContainer

        container = AppContainer.from_config(
            str(config_path / "mock_motor_config.yaml")
        )
        assert isinstance(container, QtAppContainer)

    def test_from_config_controller(
        self, mock_entry_points: Any, config_path: Path
    ) -> None:
        container = AppContainer.from_config(
            str(config_path / "mock_controller_config.yaml")
        )
        container.build()
        assert len(container.presenters) == 1

    def test_from_config_unknown_frontend_raises(
        self, mock_entry_points: Any, config_path: Path, tmp_path: Path
    ) -> None:
        import yaml

        cfg = {"frontend": "unknown_frontend"}
        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text(yaml.dump(cfg))

        with pytest.raises(ValueError, match="Unknown frontend"):
            AppContainer.from_config(str(cfg_file))
