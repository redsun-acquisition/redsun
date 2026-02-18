"""Tests for the container-based architecture."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from redsun.containers import AppContainer, component
from redsun.containers.components import (
    _DeviceComponent,
    _PresenterComponent,
    _ViewComponent,
)

class TestComponentWrappers:
    """Tests for _DeviceComponent, _PresenterComponent, _ViewComponent."""

    def test_device_component_pending_repr(self) -> None:
        from mock_pkg.device import MyMotor

        comp = _DeviceComponent(
            MyMotor, "m", None, axis=["X"], step_size={"X": 0.1},
            egu="mm", integer=1, floating=1.0, string="s",
        )
        assert "pending" in repr(comp)

    def test_device_component_build(self) -> None:
        from mock_pkg.device import MyMotor

        comp = _DeviceComponent(
            MyMotor, "m", None, axis=["X"], step_size={"X": 0.1},
            egu="mm", integer=1, floating=1.0, string="s",
        )
        device = comp.build()
        assert device.name == "m"
        assert "built" in repr(comp)

    def test_instance_before_build_raises(self) -> None:
        from mock_pkg.device import MyMotor

        comp = _DeviceComponent(
            MyMotor, "m", None, axis=["X"], step_size={"X": 0.1},
            egu="mm", integer=1, floating=1.0, string="s",
        )
        with pytest.raises(RuntimeError, match="not been instantiated"):
            _ = comp.instance

    def test_presenter_component_build(self) -> None:
        from mock_pkg.controller import MockController

        from sunflare.virtual import VirtualBus

        comp = _PresenterComponent(
            MockController, "ctrl", None,
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
        comp = _ViewComponent(MockQtView, "v", None)
        bus = VirtualBus()
        view = comp.build(bus)
        assert view is comp.instance
        assert "built" in repr(comp)


class TestAppContainerMeta:
    """Tests for metaclass component collection."""

    def test_collects_components(self) -> None:
        from mock_pkg.controller import MockController
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = _DeviceComponent(
                MyMotor, "motor", None, axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )
            ctrl = _PresenterComponent(
                MockController, "ctrl", None,
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
            motor = _DeviceComponent(
                MyMotor, "motor", None, axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )

        class Child(Base):
            pass

        assert "motor" in Child._device_components


class TestAppContainerBuild:
    """Tests for the build lifecycle."""

    def test_build_devices_and_presenters(self) -> None:
        from mock_pkg.controller import MockController
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = _DeviceComponent(
                MyMotor, "motor", None, axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )
            ctrl = _PresenterComponent(
                MockController, "ctrl", None,
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


# ── component() field syntax ────────────────────────────────────────


class TestComponentFieldSyntax:
    """Tests for the ``component()`` field-specifier syntax."""

    def test_component_field_collects_device(self) -> None:
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = component(
                MyMotor,
                layer="device", axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )

        assert "motor" in TestApp._device_components
        assert isinstance(TestApp._device_components["motor"], _DeviceComponent)

    def test_component_field_collects_presenter(self) -> None:
        from mock_pkg.controller import MockController

        class TestApp(AppContainer):
            ctrl = component(
                MockController,
                layer="presenter",
                string="s", integer=1, floating=0.0, boolean=False,
            )

        assert "ctrl" in TestApp._presenter_components
        assert isinstance(TestApp._presenter_components["ctrl"], _PresenterComponent)

    def test_component_field_collects_view(self) -> None:
        from mock_pkg.view import MockQtView

        from qtpy.QtWidgets import QApplication

        _ = QApplication.instance() or QApplication([])

        class TestApp(AppContainer):
            v = component(MockQtView, layer="view")

        assert "v" in TestApp._view_components
        assert isinstance(TestApp._view_components["v"], _ViewComponent)

    def test_component_field_build_lifecycle(self) -> None:
        from mock_pkg.controller import MockController
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = component(
                MyMotor,
                layer="device", axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )
            ctrl = component(
                MockController,
                layer="presenter",
                string="s", integer=1, floating=0.0, boolean=False,
            )

        app = TestApp()
        assert not app.is_built

        app.build()
        assert app.is_built
        assert "motor" in app.devices
        assert app.devices["motor"].name == "motor"
        assert "ctrl" in app.presenters

    def test_component_field_mixed_with_direct_wrapper(self) -> None:
        from mock_pkg.controller import MockController
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = component(
                MyMotor,
                layer="device", axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )
            ctrl = _PresenterComponent(
                MockController, "ctrl", None,
                string="s", integer=1, floating=0.0, boolean=False,
            )

        assert "motor" in TestApp._device_components
        assert "ctrl" in TestApp._presenter_components

        app = TestApp()
        app.build()
        assert "motor" in app.devices
        assert "ctrl" in app.presenters

    def test_component_field_inherits_from_base(self) -> None:
        from mock_pkg.controller import MockController
        from mock_pkg.device import MyMotor

        class Base(AppContainer):
            motor = component(
                MyMotor,
                layer="device", axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )

        class Child(Base):
            ctrl = component(
                MockController,
                layer="presenter",
                string="s", integer=1, floating=0.0, boolean=False,
            )

        assert "motor" in Child._device_components
        assert "ctrl" in Child._presenter_components


# ── config() + from_config ──────────────────────────────────────────


class TestConfigField:
    """Tests for the ``config()`` field and ``from_config`` kwarg loading."""

    def test_from_config_loads_device_kwargs(self, config_path: Path) -> None:
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            motor = component(MyMotor, layer="device", from_config="motor")

        comp = TestApp._device_components["motor"]
        assert comp.kwargs["axis"] == ["X"]
        assert comp.kwargs["egu"] == "mm"
        assert comp.kwargs["integer"] == 42
        assert comp.kwargs["string"] == "from config"

    def test_from_config_loads_presenter_kwargs(self, config_path: Path) -> None:
        from mock_pkg.controller import MockController

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            ctrl = component(MockController, layer="presenter", from_config="ctrl")

        comp = TestApp._presenter_components["ctrl"]
        assert comp.kwargs["string"] == "config ctrl"
        assert comp.kwargs["integer"] == 10
        assert comp.kwargs["boolean"] is True

    def test_from_config_inline_overrides(self, config_path: Path) -> None:
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            motor = component(
                MyMotor,
                layer="device", from_config="motor", egu="um",
            )

        comp = TestApp._device_components["motor"]
        # inline egu="um" should override config egu="mm"
        assert comp.kwargs["egu"] == "um"
        # other config values should remain
        assert comp.kwargs["axis"] == ["X"]
        assert comp.kwargs["integer"] == 42

    def test_from_config_build_lifecycle(self, config_path: Path) -> None:
        from mock_pkg.controller import MockController
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            motor = component(MyMotor, layer="device", from_config="motor")
            ctrl = component(MockController, layer="presenter", from_config="ctrl")

        app = TestApp()
        app.build()
        assert app.is_built
        assert "motor" in app.devices
        assert app.devices["motor"].name == "motor"
        assert "ctrl" in app.presenters

    def test_from_config_without_config_field_raises(self) -> None:
        from mock_pkg.device import MyMotor

        with pytest.raises(TypeError, match="no config path was provided"):

            class TestApp(AppContainer):
                motor = component(MyMotor, layer="device", from_config="motor")

    def test_from_config_missing_section_warns(
        self, config_path: Path, caplog: pytest.LogCaptureFixture,
    ) -> None:
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            # "missing" is not a key in the config file
            missing = component(
                MyMotor,
                layer="device", from_config="missing",
                axis=["Y"], step_size={"Y": 0.2},
                egu="deg", integer=0, floating=0.0, string="fallback",
            )

        assert "No config section 'missing'" in caplog.text
        # should still work with just the inline kwargs
        comp = TestApp._device_components["missing"]
        assert comp.kwargs["egu"] == "deg"


# ── top-level public API ────────────────────────────────────────────


class TestTopLevelImports:
    """Tests that the main APIs are importable directly from redsun."""

    def test_appcontainer_importable_from_redsun(self) -> None:
        from redsun import AppContainer as AC

        assert AC is AppContainer

    def test_component_importable_from_redsun(self) -> None:
        from redsun import component as c

        assert c is component

    def test_redsun_config_not_in_public_api(self) -> None:
        import redsun

        assert not hasattr(redsun, "RedSunConfig")
        assert "RedSunConfig" not in redsun.__all__

    def test_top_level_import_works_end_to_end(self) -> None:
        """Smoke test: define and build a container using only top-level imports."""
        from mock_pkg.controller import MockController
        from mock_pkg.device import MyMotor

        from redsun import AppContainer as AC
        from redsun import component as c

        class TestApp(AC):
            motor = c(MyMotor, layer="device", axis=["X"], step_size={"X": 0.1},
                      egu="mm", integer=1, floating=1.0, string="s")
            ctrl = c(MockController, layer="presenter",
                     string="s", integer=1, floating=0.0, boolean=False)

        app = TestApp()
        app.build()
        assert "motor" in app.devices
        assert "ctrl" in app.presenters

