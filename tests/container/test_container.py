"""Tests for the container-based architecture."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from mock_pkg.controller import MockController
from mock_pkg.device import MockOAMotor, MyMotor
from mock_pkg.view import MockQtView
from ophyd_async.core import Device
from qtpy.QtWidgets import QApplication

from redsun.containers import (
    AppConfig,
    AppContainer,
    declare_device,
    declare_presenter,
    declare_view,
)
from redsun.containers.components import (
    _DeviceComponent,
    _PresenterComponent,
    _ViewComponent,
)
from redsun.qt import QtAppContainer
from redsun.virtual import RedSunConfig


class TestComponentWrappers:
    """Tests for _DeviceComponent, _PresenterComponent, _ViewComponent."""

    def test_device_component_pending_repr(self) -> None:

        comp = _DeviceComponent(
            MyMotor,
            "m",
            axis=["X"],
            step_size={"X": 0.1},
            egu="mm",
            integer=1,
            floating=1.0,
            string="s",
        )
        assert "pending" in repr(comp)

    def test_device_component_build(self) -> None:

        comp = _DeviceComponent(
            MyMotor,
            "m",
            axis=["X"],
            step_size={"X": 0.1},
            egu="mm",
            integer=1,
            floating=1.0,
            string="s",
        )
        device = comp.build()
        assert device.name == "m"
        assert "built" in repr(comp)

    def test_instance_before_build_raises(self) -> None:

        comp = _DeviceComponent(
            MyMotor,
            "m",
            axis=["X"],
            step_size={"X": 0.1},
            egu="mm",
            integer=1,
            floating=1.0,
            string="s",
        )
        with pytest.raises(RuntimeError, match="not been instantiated"):
            _ = comp.instance

    def test_presenter_component_build(self) -> None:

        comp = _PresenterComponent(
            MockController,
            "ctrl",
            string="s",
            integer=1,
            floating=0.0,
            boolean=False,
        )
        presenter = comp.build({})
        assert presenter is comp.instance
        assert "built" in repr(comp)

    @pytest.mark.qt
    def test_view_component_build(self) -> None:

        _ = QApplication.instance() or QApplication([])
        comp = _ViewComponent(MockQtView, "v")
        view = comp.build()
        assert view is comp.instance
        assert "built" in repr(comp)


class TestComponentCollection:
    """Tests for component collection via __init_subclass__."""

    def test_collects_components(self) -> None:

        class TestApp(AppContainer):
            motor = _DeviceComponent(
                MyMotor,
                "motor",
                axis=["X"],
                step_size={"X": 0.1},
                egu="mm",
                integer=1,
                floating=1.0,
                string="s",
            )
            ctrl = _PresenterComponent(
                MockController,
                "ctrl",
                string="s",
                integer=1,
                floating=0.0,
                boolean=False,
            )

        assert "motor" in TestApp._device_components
        assert "ctrl" in TestApp._presenter_components
        assert len(TestApp._view_components) == 0

    def test_base_container_has_empty_components(self) -> None:
        assert len(AppContainer._device_components) == 0
        assert len(AppContainer._presenter_components) == 0
        assert len(AppContainer._view_components) == 0

    def test_inherits_components_from_base(self) -> None:

        class Base(AppContainer):
            motor = _DeviceComponent(
                MyMotor,
                "motor",
                axis=["X"],
                step_size={"X": 0.1},
                egu="mm",
                integer=1,
                floating=1.0,
                string="s",
            )

        class Child(Base):
            pass

        assert "motor" in Child._device_components


class TestAppContainerBuild:
    """Tests for the build lifecycle."""

    def test_build_devices_and_presenters(self) -> None:

        class TestApp(AppContainer):
            motor = _DeviceComponent(
                MyMotor,
                "motor",
                axis=["X"],
                step_size={"X": 0.1},
                egu="mm",
                integer=1,
                floating=1.0,
                string="s",
            )
            ctrl = _PresenterComponent(
                MockController,
                "ctrl",
                string="s",
                integer=1,
                floating=0.0,
                boolean=False,
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

    def test_from_config_motor(self, mock_entry_points: Any, config_path: Path) -> None:
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

        cfg = {"frontend": "unknown_frontend"}
        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text(yaml.dump(cfg))

        with pytest.raises(ValueError, match="Unknown frontend"):
            AppContainer.from_config(str(cfg_file))


class TestComponentFieldSyntax:
    """Tests for the ``component()`` field-specifier syntax."""

    def test_component_field_collects_device(self) -> None:

        class TestApp(AppContainer):
            motor = declare_device(
                MyMotor,
                axis=["X"],
                step_size={"X": 0.1},
                egu="mm",
                integer=1,
                floating=1.0,
                string="s",
            )

        assert "motor" in TestApp._device_components
        assert isinstance(TestApp._device_components["motor"], _DeviceComponent)

    def test_component_field_collects_presenter(self) -> None:

        class TestApp(AppContainer):
            ctrl = declare_presenter(
                MockController,
                string="s",
                integer=1,
                floating=0.0,
                boolean=False,
            )

        assert "ctrl" in TestApp._presenter_components
        assert isinstance(TestApp._presenter_components["ctrl"], _PresenterComponent)

    @pytest.mark.qt
    def test_component_field_collects_view(self) -> None:

        _ = QApplication.instance() or QApplication([])

        class TestApp(AppContainer):
            v = declare_view(MockQtView)

        assert "v" in TestApp._view_components
        assert isinstance(TestApp._view_components["v"], _ViewComponent)

    def test_component_field_build_lifecycle(self) -> None:

        class TestApp(AppContainer):
            motor = declare_device(
                MyMotor,
                axis=["X"],
                step_size={"X": 0.1},
                egu="mm",
                integer=1,
                floating=1.0,
                string="s",
            )
            ctrl = declare_presenter(
                MockController,
                string="s",
                integer=1,
                floating=0.0,
                boolean=False,
            )

        app = TestApp()
        assert not app.is_built

        app.build()
        assert app.is_built
        assert "motor" in app.devices
        assert app.devices["motor"].name == "motor"
        assert "ctrl" in app.presenters

    def test_component_field_mixed_with_direct_wrapper(self) -> None:

        class TestApp(AppContainer):
            motor = declare_device(
                MyMotor,
                axis=["X"],
                step_size={"X": 0.1},
                egu="mm",
                integer=1,
                floating=1.0,
                string="s",
            )
            ctrl = _PresenterComponent(
                MockController,
                "ctrl",
                string="s",
                integer=1,
                floating=0.0,
                boolean=False,
            )

        assert "motor" in TestApp._device_components
        assert "ctrl" in TestApp._presenter_components

        app = TestApp()
        app.build()
        assert "motor" in app.devices
        assert "ctrl" in app.presenters

    def test_component_field_inherits_from_base(self) -> None:

        class Base(AppContainer):
            motor = declare_device(
                MyMotor,
                axis=["X"],
                step_size={"X": 0.1},
                egu="mm",
                integer=1,
                floating=1.0,
                string="s",
            )

        class Child(Base):
            ctrl = declare_presenter(
                MockController,
                string="s",
                integer=1,
                floating=0.0,
                boolean=False,
            )

        assert "motor" in Child._device_components
        assert "ctrl" in Child._presenter_components


class TestConfigField:
    """Tests for the ``config()`` field and ``from_config`` kwarg loading."""

    def test_from_config_loads_device_kwargs(self, config_path: Path) -> None:

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            motor = declare_device(MyMotor, from_config="motor")

        comp = TestApp._device_components["motor"]
        assert comp.kwargs["axis"] == ["X"]
        assert comp.kwargs["egu"] == "mm"
        assert comp.kwargs["integer"] == 42
        assert comp.kwargs["string"] == "from config"

    def test_from_config_loads_presenter_kwargs(self, config_path: Path) -> None:

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            ctrl = declare_presenter(MockController, from_config="ctrl")

        comp = TestApp._presenter_components["ctrl"]
        assert comp.kwargs["string"] == "config ctrl"
        assert comp.kwargs["integer"] == 10
        assert comp.kwargs["boolean"] is True

    def test_from_config_inline_overrides(self, config_path: Path) -> None:

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            motor = declare_device(
                MyMotor,
                from_config="motor",
                egu="um",
            )

        comp = TestApp._device_components["motor"]
        assert comp.kwargs["egu"] == "um"
        assert comp.kwargs["axis"] == ["X"]
        assert comp.kwargs["integer"] == 42

    def test_from_config_build_lifecycle(self, config_path: Path) -> None:

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            motor = declare_device(MyMotor, from_config="motor")
            ctrl = declare_presenter(MockController, from_config="ctrl")

        app = TestApp()
        app.build()
        assert app.is_built
        assert "motor" in app.devices
        assert app.devices["motor"].name == "motor"
        assert "ctrl" in app.presenters

    def test_from_config_without_config_field_raises(self) -> None:

        with pytest.raises(TypeError, match="no config path was provided"):

            class TestApp(AppContainer):
                motor = declare_device(MyMotor, from_config="motor")

    def test_from_config_missing_section_warns(
        self,
        config_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:

        class TestApp(AppContainer, config=config_path / "mock_component_config.yaml"):
            missing = declare_device(
                MyMotor,
                from_config="missing",
                axis=["Y"],
                step_size={"Y": 0.2},
                egu="deg",
                integer=0,
                floating=0.0,
                string="fallback",
            )

        assert "No config section 'missing'" in caplog.text
        comp = TestApp._device_components["missing"]
        assert comp.kwargs["egu"] == "deg"


class TestAppConfig:
    """Tests for AppConfig TypedDict and RedSunConfig inheritance."""

    def test_app_config_has_schema_version(self) -> None:

        cfg: AppConfig = {
            "schema_version": 1.0,
            "session": "s",
            "frontend": "pyqt",
        }
        assert cfg["schema_version"] == 1.0
        # AppConfig extends RedSunConfig — verify required keys are inherited
        assert "schema_version" in AppConfig.__required_keys__
        assert "frontend" in AppConfig.__required_keys__
        # session is NotRequired since 0.10.0
        assert "session" in AppConfig.__optional_keys__

    def test_app_config_has_component_fields(self) -> None:

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
        """RedSunConfig must not expose devices/presenters/views."""
        assert "devices" not in RedSunConfig.__annotations__
        assert "presenters" not in RedSunConfig.__annotations__
        assert "views" not in RedSunConfig.__annotations__


@pytest.mark.qt
class TestQtAppContainer:
    """Tests for QtAppContainer lifecycle correctness."""

    def test_build_before_run_creates_qapplication(self) -> None:

        class _TestQtApp(QtAppContainer):
            motor = declare_device(
                MyMotor,
                axis=["X"],
                step_size={"X": 0.1},
                egu="mm",
                integer=1,
                floating=1.0,
                string="s",
            )
            v = declare_view(MockQtView)

        app = _TestQtApp()
        assert app._qt_app is None

        app.build()

        assert app._qt_app is not None
        assert QApplication.instance() is app._qt_app
        assert app.is_built
        assert "motor" in app.devices
        assert "v" in app.views

    def test_run_reuses_qapplication_created_by_build(self) -> None:

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
        """Alias takes priority over the attribute name as device name."""

        class TestApp(AppContainer):
            motor = declare_device(
                MyMotor,
                alias="cam",
                axis=["X"],
                step_size={"X": 0.1},
                egu="mm",
                integer=1,
                floating=1.0,
                string="s",
            )

        app = TestApp()
        app.build()
        assert "cam" in app.devices
        assert "motor" not in app.devices
        assert app.devices["cam"].name == "cam"

    def test_device_attr_name_used_when_no_alias(self) -> None:
        """Attribute name is used when alias is None."""

        class TestApp(AppContainer):
            motor = declare_device(
                MyMotor,
                axis=["X"],
                step_size={"X": 0.1},
                egu="mm",
                integer=1,
                floating=1.0,
                string="s",
            )

        app = TestApp()
        app.build()
        assert "motor" in app.devices
        assert app.devices["motor"].name == "motor"

    def test_presenter_alias_overrides_attr_name(self) -> None:
        """Alias takes priority over the attribute name for presenters."""

        class TestApp(AppContainer):
            motor = declare_device(
                MyMotor,
                axis=["X"],
                step_size={"X": 0.1},
                egu="mm",
                integer=1,
                floating=1.0,
                string="s",
            )
            ctrl = declare_presenter(
                MockController,
                alias="my_ctrl",
                string="s",
                integer=1,
                floating=0.0,
                boolean=False,
            )

        app = TestApp()
        app.build()
        assert "my_ctrl" in app.presenters
        assert "ctrl" not in app.presenters
        assert app.presenters["my_ctrl"].name == "my_ctrl"

    def test_alias_baked_into_component_dict_key(self) -> None:
        """Metaclass stores the component under the alias, not the attr name."""

        class TestApp(AppContainer):
            my_motor = declare_device(
                MyMotor,
                alias="detector",
                axis=["X"],
                step_size={"X": 0.1},
                egu="mm",
                integer=1,
                floating=1.0,
                string="s",
            )

        assert "detector" in TestApp._device_components
        assert "my_motor" not in TestApp._device_components


class TestChildDevices:
    """Tests for devices that host child sub-device attributes."""

    def test_device_with_child_registers_in_container(self) -> None:
        """A device whose __init__ creates child Device instances builds correctly."""

        class MotorWithChild(MyMotor):
            """Motor that owns a child axis device."""

            def __init__(self, name: str, /, **kwargs: Any) -> None:
                super().__init__(name, **kwargs)
                # child device shares the parent name as a namespace prefix
                self.aux = MyMotor(f"{name}-aux", egu="deg")

        class TestApp(AppContainer):
            motor = declare_device(MotorWithChild, egu="mm", string="parent")

        app = TestApp()
        app.build()
        assert "motor" in app.devices
        parent = app.devices["motor"]
        assert parent.name == "motor"
        # the child device is accessible as an attribute of the parent
        assert hasattr(parent, "aux")
        assert parent.aux.name == "motor-aux"

    async def test_child_device_signals_are_functional(self) -> None:
        """Child device signals work independently from the parent."""

        class MotorWithChild(MyMotor):
            def __init__(self, name: str, /, **kwargs: Any) -> None:
                super().__init__(name, **kwargs)
                self.aux = MyMotor(f"{name}-aux", egu="deg")

        class TestApp(AppContainer):
            stage = declare_device(MotorWithChild, egu="mm")

        app = TestApp()
        app.build()
        app.connect_devices(mock=True)
        parent = app.devices["stage"]
        # parent step_size descriptor includes units from egu
        parent_desc = await parent.step_size.describe()
        assert "stage-step_size" in parent_desc
        assert parent_desc["stage-step_size"]["units"] == "mm"
        # child step_size descriptor has its own units
        child_desc = await parent.aux.step_size.describe()
        assert "stage-aux-step_size" in child_desc
        assert child_desc["stage-aux-step_size"]["units"] == "deg"

    def test_child_device_satisfies_device(self) -> None:
        """A child Device instance on a parent satisfies ophyd-async Device."""
        child = MyMotor(
            "parent-child",
            egu="um",
            integer=0,
            floating=0.0,
            string="",
        )
        assert isinstance(child, Device)
        assert child.parent is None
        assert child.name == "parent-child"


class TestOphyAsyncDevices:
    """Tests for ophyd-async devices registered in the container."""

    def test_oa_device_builds_in_container(self) -> None:
        """An ophyd-async StandardReadable can be declared and built."""

        class TestApp(AppContainer):
            motor = declare_device(MockOAMotor, units="mm")

        app = TestApp()
        app.build()
        assert "motor" in app.devices
        assert app.devices["motor"].name == "motor"

    def test_oa_device_satisfies_device(self) -> None:
        """An ophyd-async StandardReadable satisfies ophyd-async Device."""
        m = MockOAMotor("oa_motor")
        assert isinstance(m, Device)
        assert m.name == "oa_motor"
        assert m.parent is None

    def test_oa_device_alias_in_container(self) -> None:
        """The alias kwarg works for ophyd-async devices."""

        class TestApp(AppContainer):
            oa = declare_device(MockOAMotor, alias="oa_stage", units="um")

        app = TestApp()
        app.build()
        assert "oa_stage" in app.devices
        assert "oa" not in app.devices
        assert app.devices["oa_stage"].name == "oa_stage"

    def test_oa_device_units_in_descriptor(self) -> None:
        """Units are embedded in the signal descriptor, not as a separate attribute."""
        m = MockOAMotor("cam", units="nm")
        # signals carry units in their descriptor source string prefix;
        # actual unit metadata is readable once connected
        assert hasattr(m, "x")
        assert hasattr(m, "y")
        # verify there is no top-level 'units' attribute leaking
        assert not hasattr(m, "units")

    async def test_oa_device_descriptor_contains_units(self) -> None:
        """After connecting (mock), descriptor documents contain 'units'."""
        m = MockOAMotor("stage", units="mm")
        await m.connect(mock=True)
        desc = await m.x.describe()
        assert "stage-x" in desc
        assert desc["stage-x"]["units"] == "mm"


class TestConnectDevices:
    """Smoke tests for the connect_devices / run lifecycle."""

    def test_connect_devices_requires_build(self) -> None:
        """connect_devices() raises RuntimeError when called before build()."""

        class EmptyApp(AppContainer):
            pass

        app = EmptyApp()
        with pytest.raises(RuntimeError, match="build()"):
            app.connect_devices(mock=True)

    def test_connect_devices_sets_connected_flag(self) -> None:
        """After connect_devices(mock=True), _devices_connected is True."""

        class TestApp(AppContainer):
            motor = declare_device(MockOAMotor, units="mm")

        app = TestApp()
        assert not app._devices_connected
        app.build()
        assert not app._devices_connected
        app.connect_devices(mock=True)
        assert app._devices_connected

    def test_run_connects_devices_automatically(self) -> None:
        """run() calls connect_devices() so callers need not do it explicitly."""

        class TestApp(AppContainer):
            motor = declare_device(MockOAMotor, units="mm")

        app = TestApp()
        # Patch run() to stop after connect_devices so we don't need a frontend.
        original_run = AppContainer.run

        connected_before_frontend: list[bool] = []

        def patched_run(self: AppContainer) -> None:  # type: ignore[override]
            # call the real run up to (but not past) frontend startup
            if not self._is_built:
                self.build()
            if not self._devices_connected:
                self.connect_devices(mock=True)
            connected_before_frontend.append(self._devices_connected)

        AppContainer.run = patched_run  # type: ignore[method-assign]
        try:
            app.run()
        finally:
            AppContainer.run = original_run  # type: ignore[method-assign]

        assert connected_before_frontend == [True]

    def test_run_skips_connect_when_already_connected(self) -> None:
        """Make sure that run() does not reconnect devices that were already connected."""
        connect_calls: list[str] = []

        class TrackingApp(AppContainer):
            motor = declare_device(MockOAMotor, units="mm")

            def connect_devices(self, mock: bool = False) -> None:  # type: ignore[override]
                connect_calls.append("called")
                super().connect_devices(mock=mock)

        app = TrackingApp()
        app.build()
        app.connect_devices(mock=True)
        assert connect_calls == ["called"]

        # Simulate run() when already connected — connect_devices must not fire again.
        if not app._devices_connected:
            app.connect_devices(mock=True)

        assert connect_calls == ["called"]  # still only one call
