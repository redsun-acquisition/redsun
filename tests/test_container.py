"""Tests for the container-based architecture."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

from redsun.containers import AppContainer, AppConfig, StorageConfig, device, presenter, view
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
            MyMotor, "m", axis=["X"], step_size={"X": 0.1},
            egu="mm", integer=1, floating=1.0, string="s",
        )
        assert "pending" in repr(comp)

    def test_device_component_build(self) -> None:
        from mock_pkg.device import MyMotor

        comp = _DeviceComponent(
            MyMotor, "m", axis=["X"], step_size={"X": 0.1},
            egu="mm", integer=1, floating=1.0, string="s",
        )
        device = comp.build()
        assert device.name == "m"
        assert "built" in repr(comp)

    def test_instance_before_build_raises(self) -> None:
        from mock_pkg.device import MyMotor

        comp = _DeviceComponent(
            MyMotor, "m", axis=["X"], step_size={"X": 0.1},
            egu="mm", integer=1, floating=1.0, string="s",
        )
        with pytest.raises(RuntimeError, match="not been instantiated"):
            _ = comp.instance

    def test_presenter_component_build(self) -> None:
        from mock_pkg.controller import MockController

        comp = _PresenterComponent(
            MockController, "ctrl",
            string="s", integer=1, floating=0.0, boolean=False,
        )
        presenter = comp.build({})
        assert presenter is comp.instance
        assert "built" in repr(comp)

    @pytest.mark.skipif(
        sys.platform == "linux" and not os.environ.get("DISPLAY"),
        reason="requires a display (Qt)",
    )
    def test_view_component_build(self) -> None:
        from mock_pkg.view import MockQtView
        from qtpy.QtWidgets import QApplication

        _ = QApplication.instance() or QApplication([])
        comp = _ViewComponent(MockQtView, "v")
        view = comp.build()
        assert view is comp.instance
        assert "built" in repr(comp)


class TestAppContainerMeta:
    """Tests for metaclass component collection."""

    def test_collects_components(self) -> None:
        from mock_pkg.controller import MockController
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = _DeviceComponent(
                MyMotor, "motor", axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )
            ctrl = _PresenterComponent(
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
            motor = _DeviceComponent(
                MyMotor, "motor", axis=["X"], step_size={"X": 0.1},
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
                MyMotor, "motor", axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )
            ctrl = _PresenterComponent(
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
            _ = app.virtual_container

    def test_config_defaults(self) -> None:
        app = AppContainer()
        assert app.config["session"] == "Redsun"
        assert app.config["frontend"] == "pyqt"
        assert app.config["schema_version"] == 1.0

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

    def test_virtual_container_carries_config(self) -> None:
        """After build(), virtual_container.configuration holds base config fields."""
        class EmptyApp(AppContainer):
            pass

        app = EmptyApp(session="TestSession", frontend="pyqt")
        app.build()
        assert app.virtual_container.session == "TestSession"
        assert app.virtual_container.frontend == "pyqt"
        assert app.virtual_container.schema_version == 1.0


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
        from redsun.qt import QtAppContainer

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


class TestComponentFieldSyntax:
    """Tests for the ``component()`` field-specifier syntax."""

    def test_component_field_collects_device(self) -> None:
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = device(
                MyMotor,
                axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )

        assert "motor" in TestApp._device_components
        assert isinstance(TestApp._device_components["motor"], _DeviceComponent)

    def test_component_field_collects_presenter(self) -> None:
        from mock_pkg.controller import MockController

        class TestApp(AppContainer):
            ctrl = presenter(
                MockController,
                string="s", integer=1, floating=0.0, boolean=False,
            )

        assert "ctrl" in TestApp._presenter_components
        assert isinstance(TestApp._presenter_components["ctrl"], _PresenterComponent)

    @pytest.mark.skipif(
        sys.platform == "linux" and not os.environ.get("DISPLAY"),
        reason="Fails on Linux CI without a display (Qt required for view components)",
    )
    def test_component_field_collects_view(self) -> None:
        from mock_pkg.view import MockQtView
        from qtpy.QtWidgets import QApplication

        _ = QApplication.instance() or QApplication([])

        class TestApp(AppContainer):
            v = view(MockQtView)

        assert "v" in TestApp._view_components
        assert isinstance(TestApp._view_components["v"], _ViewComponent)

    def test_component_field_build_lifecycle(self) -> None:
        from mock_pkg.controller import MockController
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = device(
                MyMotor, axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )
            ctrl = presenter(
                MockController,
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
            motor = device(
                MyMotor, axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )
            ctrl = _PresenterComponent(
                MockController, "ctrl",
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
            motor = device(
                MyMotor, axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )

        class Child(Base):
            ctrl = presenter(
                MockController,
                string="s", integer=1, floating=0.0, boolean=False,
            )

        assert "motor" in Child._device_components
        assert "ctrl" in Child._presenter_components


class TestConfigField:
    """Tests for the ``config()`` field and ``from_config`` kwarg loading."""

    def test_from_config_loads_device_kwargs(self, config_path: Path) -> None:
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            motor = device(MyMotor, from_config="motor")

        comp = TestApp._device_components["motor"]
        assert comp.kwargs["axis"] == ["X"]
        assert comp.kwargs["egu"] == "mm"
        assert comp.kwargs["integer"] == 42
        assert comp.kwargs["string"] == "from config"

    def test_from_config_loads_presenter_kwargs(self, config_path: Path) -> None:
        from mock_pkg.controller import MockController

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            ctrl = presenter(MockController, from_config="ctrl")

        comp = TestApp._presenter_components["ctrl"]
        assert comp.kwargs["string"] == "config ctrl"
        assert comp.kwargs["integer"] == 10
        assert comp.kwargs["boolean"] is True

    def test_from_config_inline_overrides(self, config_path: Path) -> None:
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            motor = device(
                MyMotor, from_config="motor", egu="um",
            )

        comp = TestApp._device_components["motor"]
        assert comp.kwargs["egu"] == "um"
        assert comp.kwargs["axis"] == ["X"]
        assert comp.kwargs["integer"] == 42

    def test_from_config_build_lifecycle(self, config_path: Path) -> None:
        from mock_pkg.controller import MockController
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            motor = device(MyMotor, from_config="motor")
            ctrl = presenter(MockController, from_config="ctrl")

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
                motor = device(MyMotor, from_config="motor")

    def test_from_config_missing_section_warns(
        self, config_path: Path, caplog: pytest.LogCaptureFixture,
    ) -> None:
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            missing = device(
                MyMotor, from_config="missing",
                axis=["Y"], step_size={"Y": 0.2},
                egu="deg", integer=0, floating=0.0, string="fallback",
            )

        assert "No config section 'missing'" in caplog.text
        comp = TestApp._device_components["missing"]
        assert comp.kwargs["egu"] == "deg"


class TestAppConfig:
    """Tests for AppConfig TypedDict and RedSunConfig inheritance."""

    def test_app_config_has_schema_version(self) -> None:
        from redsun.containers import AppConfig
        from sunflare.virtual import RedSunConfig

        cfg: AppConfig = {
            "schema_version": 1.0,
            "session": "s",
            "frontend": "pyqt",
        }
        assert cfg["schema_version"] == 1.0
        # AppConfig extends RedSunConfig — verify required keys are inherited
        assert "schema_version" in AppConfig.__required_keys__
        assert "frontend" in AppConfig.__required_keys__
        # session is NotRequired in sunflare 0.10.0
        assert "session" in AppConfig.__optional_keys__

    def test_app_config_has_component_fields(self) -> None:
        from redsun.containers import AppConfig

        cfg: AppConfig = {
            "schema_version": 1.0,
            "session": "s",
            "frontend": "pyqt",
            "devices": {"cam": {}},
            "presenters": {},
            "views": {},
        }
        assert "devices" in cfg
        assert "cam" in cfg["devices"]

    def test_redsun_config_no_component_fields(self) -> None:
        """RedSunConfig in sunflare must not expose devices/presenters/views."""
        from sunflare.virtual import RedSunConfig
        assert "devices" not in RedSunConfig.__annotations__
        assert "presenters" not in RedSunConfig.__annotations__
        assert "views" not in RedSunConfig.__annotations__


class TestQtAppContainer:
    """Tests for QtAppContainer lifecycle correctness."""

    def test_build_before_run_creates_qapplication(self) -> None:
        from mock_pkg.view import MockQtView
        from mock_pkg.device import MyMotor

        from qtpy.QtWidgets import QApplication
        from redsun.qt import QtAppContainer

        class _TestQtApp(QtAppContainer):
            motor = device(
                MyMotor, axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )
            v = view(MockQtView)

        app = _TestQtApp()
        assert app._qt_app is None

        app.build()

        assert app._qt_app is not None
        assert QApplication.instance() is app._qt_app
        assert app.is_built
        assert "motor" in app.devices
        assert "v" in app.views

    def test_run_reuses_qapplication_created_by_build(self) -> None:
        from qtpy.QtWidgets import QApplication
        from redsun.qt import QtAppContainer

        class _TestQtApp(QtAppContainer):
            pass

        app = _TestQtApp()
        app.build()
        first_instance = app._qt_app

        assert QApplication.instance() is first_instance


class TestComponentNaming:
    """Tests for component naming priority: alias > attribute name.

    For ``from_config()``, the YAML key becomes the component name.
    For declarative syntax, ``alias`` wins over the attribute name.
    """

    def test_device_alias_overrides_attr_name(self) -> None:
        """alias takes priority over the attribute name as device name."""
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = device(
                MyMotor, alias="cam",
                axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )

        app = TestApp()
        app.build()
        assert "cam" in app.devices
        assert "motor" not in app.devices
        assert app.devices["cam"].name == "cam"

    def test_device_attr_name_used_when_no_alias(self) -> None:
        """Attribute name is used when alias is None."""
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = device(
                MyMotor,
                axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )

        app = TestApp()
        app.build()
        assert "motor" in app.devices
        assert app.devices["motor"].name == "motor"

    def test_presenter_alias_overrides_attr_name(self) -> None:
        """alias takes priority over the attribute name for presenters."""
        from mock_pkg.controller import MockController
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = device(
                MyMotor, axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )
            ctrl = presenter(
                MockController, alias="my_ctrl",
                string="s", integer=1, floating=0.0, boolean=False,
            )

        app = TestApp()
        app.build()
        assert "my_ctrl" in app.presenters
        assert "ctrl" not in app.presenters
        assert app.presenters["my_ctrl"].name == "my_ctrl"

    def test_alias_baked_into_component_dict_key(self) -> None:
        """Metaclass stores the component under the alias, not the attr name."""
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            my_motor = device(
                MyMotor, alias="detector",
                axis=["X"], step_size={"X": 0.1},
                egu="mm", integer=1, floating=1.0, string="s",
            )

        assert "detector" in TestApp._device_components
        assert "my_motor" not in TestApp._device_components


class TestStorageInjection:
    """Tests for storage writer injection into devices."""

    @pytest.fixture
    def mock_writer(self):
        """Patch _build_writer to return a MagicMock, avoiding acquire-zarr dependency."""
        from unittest.mock import MagicMock, patch
        from sunflare.storage import Writer

        writer = MagicMock(spec=Writer)
        with patch("redsun.containers.container._build_writer", return_value=writer):
            yield writer

    def test_storage_injected_into_device_with_descriptor(
        self, tmp_path: Path, mock_writer: Any
    ) -> None:
        """Writer is injected into a device that declares StorageDescriptor."""
        from mock_pkg.device import MockDetectorWithStorage

        class TestApp(AppContainer):
            cam = device(
                MockDetectorWithStorage,
                sensor_shape=(512, 512),
                pixel_size=(6.5, 6.5, 6.5),
                exposure=100.0,
                egu="ms",
                integer=1,
                floating=1.0,
                string="test",
            )

        app = TestApp(session="test-session")
        app._config["storage"] = StorageConfig(
            backend="zarr",
            base_path=str(tmp_path),
            filename_provider="auto_increment",
        )
        app.build()

        cam = app.devices["cam"]
        assert cam.storage is mock_writer  # type: ignore[union-attr]

    def test_storage_not_injected_into_device_without_descriptor(
        self, tmp_path: Path, mock_writer: Any
    ) -> None:
        """Devices without StorageDescriptor are unaffected by storage config."""
        from mock_pkg.device import MyMotor

        class TestApp(AppContainer):
            motor = device(
                MyMotor,
                axis=["X"],
                step_size={"X": 1.0},
                egu="um",
                integer=1,
                floating=1.0,
                string="test",
            )

        app = TestApp(session="test-session")
        app._config["storage"] = StorageConfig(
            backend="zarr",
            base_path=str(tmp_path),
            filename_provider="auto_increment",
        )
        app.build()

        motor = app.devices["motor"]
        assert not hasattr(motor, "storage")

    def test_storage_none_when_no_config(self) -> None:
        """Without a storage section, device.storage remains None."""
        from mock_pkg.device import MockDetectorWithStorage

        class TestApp(AppContainer):
            cam = device(
                MockDetectorWithStorage,
                sensor_shape=(512, 512),
                pixel_size=(6.5, 6.5, 6.5),
                exposure=100.0,
                egu="ms",
                integer=1,
                floating=1.0,
                string="test",
            )

        app = TestApp()
        app.build()

        cam = app.devices["cam"]
        assert cam.storage is None  # type: ignore[union-attr]

    def test_storage_injected_via_inheritance(
        self, tmp_path: Path, mock_writer: Any
    ) -> None:
        """StorageDescriptor declared on a base class is still found via MRO."""
        from mock_pkg.device import MockDetectorWithStorage

        class ExtendedDetector(MockDetectorWithStorage):
            """Subclass that inherits StorageDescriptor from MockDetectorWithStorage."""
            pass

        class TestApp(AppContainer):
            cam = device(
                ExtendedDetector,
                sensor_shape=(512, 512),
                pixel_size=(6.5, 6.5, 6.5),
                exposure=100.0,
                egu="ms",
                integer=1,
                floating=1.0,
                string="test",
            )

        app = TestApp(session="test-session")
        app._config["storage"] = StorageConfig(
            backend="zarr",
            base_path=str(tmp_path),
            filename_provider="auto_increment",
        )
        app.build()

        cam = app.devices["cam"]
        assert cam.storage is mock_writer  # type: ignore[union-attr]

    def test_default_base_path_uses_session_name(self) -> None:
        """When base_path is omitted, _build_writer is called with the session name."""
        from unittest.mock import MagicMock, patch, call
        from sunflare.storage import Writer
        from mock_pkg.device import MockDetectorWithStorage

        writer = MagicMock(spec=Writer)

        class TestApp(AppContainer):
            cam = device(
                MockDetectorWithStorage,
                sensor_shape=(512, 512),
                pixel_size=(6.5, 6.5, 6.5),
                exposure=100.0,
                egu="ms",
                integer=1,
                floating=1.0,
                string="test",
            )

        app = TestApp(session="my-session")
        app._config["storage"] = StorageConfig(backend="zarr")

        with patch(
            "redsun.containers.container._build_writer", return_value=writer
        ) as mock_build:
            app.build()

        mock_build.assert_called_once()
        _, called_session = mock_build.call_args.args
        assert called_session == "my-session"

    def test_build_writer_creates_session_directory(self, tmp_path: Path) -> None:
        """_build_writer creates ~/redsun-storage/<session> when base_path is omitted."""
        from unittest.mock import patch
        from pathlib import Path as _Path
        from redsun.containers.container import _build_writer

        storage_cfg = StorageConfig(backend="zarr")

        with patch.object(_Path, "home", return_value=tmp_path):
            # _build_writer will try to import ZarrWriter; catch the ImportError
            # since acquire-zarr is not installed in the test environment
            try:
                _build_writer(storage_cfg, "my-session")
            except ImportError:
                pass

        expected = tmp_path / "redsun-storage" / "my-session"
        assert expected.exists()

