"""Tests for the container-based architecture."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml
from helpers import component
from mock_pkg.controller import (
    AsyncMotorController,
    BrokenController,
    GroupedController,
    MockController,
)
from mock_pkg.device import BrokenDevice, MockOAMotor, MyMotor
from mock_pkg.view import BrokenView, MockMotorView, MockQtView
from ophyd_async.core import Device
from qtpy.QtWidgets import QApplication

from redsun.containers import (
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
from redsun.presenter import PPresenter
from redsun.presenter.builtins import StoragePresenter
from redsun.qt import QtAppContainer
from redsun.storage import PATH_PROVIDER
from redsun.view import PView, ViewPosition
from redsun.virtual import RedSunConfig, WiringError, ports

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


class TestComponentWrappers:
    """Tests for _DeviceComponent, _PresenterComponent, _ViewComponent."""

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
        assert presenter.name == "ctrl"

    @pytest.mark.qt
    def test_view_component_build(self, qapp: QApplication) -> None:

        comp = _ViewComponent(MockQtView, "v")
        view = comp.build()
        assert view.name == "v"


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

    def test_build_reports_every_step_in_order(self) -> None:
        app = AppContainer()
        seen: list[str] = []
        app._report = seen.append

        app.build()

        assert seen == [
            "virtual container",
            "devices",
            "presenters",
            "views",
            "providers",
            "wiring",
            "injection",
        ]

    def test_a_subclass_overriding_a_phase_is_the_one_that_runs(self) -> None:
        calls: list[str] = []

        class TestApp(AppContainer):
            def _build_devices(self) -> None:
                calls.append("devices")
                super()._build_devices()

            def _apply_wiring(self) -> None:
                calls.append("wiring")
                super()._apply_wiring()

        TestApp().build()

        assert calls == ["devices", "wiring"]

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

        app = app.build()
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
        """An unnamed session is named after its class, never a shared constant."""

        class Instrument(AppContainer):
            pass

        assert AppContainer().config["name"] == "AppContainer"
        assert Instrument().config["name"] == "Instrument"
        assert AppContainer().config["frontend"] == "pyqt"
        assert AppContainer().config["schema_version"] == 1.0

    def test_a_configured_session_must_name_itself(self, tmp_path: Path) -> None:
        """It has no class of its own to be named after."""
        config = tmp_path / "unnamed.yaml"
        config.write_text("schema_version: 1.0\nfrontend: pyqt\n")
        with pytest.raises(KeyError, match="must declare 'name'"):
            AppContainer.from_config(str(config))

    def test_config_override(self) -> None:
        app = AppContainer(name="MySession", frontend="pyside")
        assert app.config["name"] == "MySession"
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

    @pytest.mark.qt
    def test_shutdown_drops_what_it_built(self, qapp: QApplication) -> None:
        """A shut-down container reports nothing built and leaves no widget.

        The declaration registries are class attributes, so a component left
        in one outlives its container and reaches the next one.
        """

        class ViewApp(AppContainer):
            ui = declare_view(MockQtView)

        before = len(QApplication.topLevelWidgets())

        app = ViewApp()
        app.build()
        assert set(app.views) == {"ui"}
        app.shutdown()

        with pytest.raises(RuntimeError):
            _ = app.views
        assert len(QApplication.topLevelWidgets()) == before

    @pytest.mark.qt
    def test_two_containers_do_not_share_components(self, qapp: QApplication) -> None:
        """Each container of a class builds and owns its own components."""

        class ViewApp(AppContainer):
            ui = declare_view(MockQtView)

        first = ViewApp()
        first.build()
        second = ViewApp()
        second.build()

        assert first.views["ui"] is not second.views["ui"]

        first.shutdown()
        assert set(second.views) == {"ui"}
        second.shutdown()

    def test_virtual_container_carries_config(self) -> None:
        """After build(), virtual_container.configuration holds base config fields."""

        class EmptyApp(AppContainer):
            pass

        app = EmptyApp(name="TestSession", frontend="pyqt")
        app.build()
        assert app.virtual_container.name == "TestSession"
        assert app.virtual_container.frontend == "pyqt"
        assert app.virtual_container.schema_version == 1.0


class TestBuildTolerance:
    """Tests for a build that carries on past a component it could not make."""

    def test_devices_lists_what_was_built(self) -> None:
        """A device that failed is absent from the mapping rather than raising."""

        class TestApp(AppContainer):
            ok = declare_device(MyMotor, egu="mm", string="s")
            bad = declare_device(BrokenDevice)

        app = TestApp().build()

        assert set(app.devices) == {"ok"}

    def test_a_presenter_that_fails_does_not_abort_the_build(self) -> None:
        """The build returns, and the presenters that built are reachable."""

        class TestApp(AppContainer):
            ok = declare_presenter(MockController)
            bad = declare_presenter(BrokenController)

        app = TestApp().build()

        assert app.is_built
        assert set(app.presenters) == {"ok"}

    @pytest.mark.qt
    def test_a_view_that_fails_does_not_abort_the_build(
        self, qapp: QApplication
    ) -> None:
        """The build returns, leaving alive the widgets of the views that built."""

        class TestApp(AppContainer):
            ok = declare_view(MockQtView)
            bad = declare_view(BrokenView)

        before = len(QApplication.topLevelWidgets())

        app = TestApp().build()

        assert app.is_built
        assert set(app.views) == {"ok"}
        assert len(QApplication.topLevelWidgets()) == before + 1

        app.shutdown()

    @pytest.mark.parametrize(
        ("declare", "expected"),
        [
            (
                lambda: declare_device(BrokenDevice),
                "Failed to build device 'bad': This device is broken",
            ),
            (
                lambda: declare_presenter(BrokenController),
                "Failed to build presenter 'bad': Broken controller",
            ),
            (
                lambda: declare_view(BrokenView),
                "Failed to build view 'bad': Broken view",
            ),
        ],
    )
    def test_a_failure_is_logged_against_the_component_name(
        self,
        declare: Callable[[], Any],
        expected: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The log names what failed and why, which is the whole report for now."""

        class TestApp(AppContainer):
            bad = declare()

        with caplog.at_level(logging.ERROR, logger="redsun"):
            TestApp().build()

        assert expected in caplog.text

    def test_the_closing_line_rises_to_warning_when_something_failed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A build that missed something says so above the level it reports at."""

        class TestApp(AppContainer):
            ok = declare_presenter(MockController)
            bad = declare_presenter(BrokenController)

        with caplog.at_level(logging.INFO, logger="redsun"):
            TestApp().build()

        closing = [r for r in caplog.records if r.message.startswith("Container built")]
        assert [r.levelno for r in closing] == [logging.WARNING]
        assert "bad (presenter)" in closing[0].message

    def test_the_closing_line_stays_at_info_when_nothing_failed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Nothing missing is not a warning."""

        class TestApp(AppContainer):
            ok = declare_presenter(MockController)

        with caplog.at_level(logging.INFO, logger="redsun"):
            TestApp().build()

        closing = [r for r in caplog.records if r.message.startswith("Container built")]
        assert [r.levelno for r in closing] == [logging.INFO]


class TestFromConfig:
    """Tests for YAML-based dynamic container creation."""

    def test_from_config_motor(
        self, mock_entry_points: None, config_path: Path
    ) -> None:
        container = AppContainer.from_config(
            str(config_path / "mock_motor_config.yaml")
        )
        assert not container.is_built
        assert container.config["frontend"] == "pyqt"

        container.build()
        assert len(container.devices) == 2

    def test_from_config_returns_qt_container(
        self, mock_entry_points: None, config_path: Path
    ) -> None:

        container = AppContainer.from_config(
            str(config_path / "mock_motor_config.yaml")
        )
        assert isinstance(container, QtAppContainer)

    def test_from_config_controller(
        self, mock_entry_points: None, config_path: Path
    ) -> None:
        container = AppContainer.from_config(
            str(config_path / "mock_controller_config.yaml")
        )
        container.build()
        assert len(container.presenters) == 1

    def test_from_config_unknown_frontend_raises(
        self, mock_entry_points: None, config_path: Path, tmp_path: Path
    ) -> None:

        cfg = {"frontend": "unknown_frontend"}
        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text(yaml.dump(cfg))

        with pytest.raises(ValueError, match="Unknown frontend"):
            AppContainer.from_config(str(cfg_file))

    def test_from_config_rejected_plugin_reports_group_expectation(
        self,
        mock_entry_points: None,
        config_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        container = AppContainer.from_config(
            str(config_path / "rejected_view_config.yaml")
        )

        assert "bad_view" not in container._view_components
        assert "cannot be loaded as a plugin in group 'views'" in caplog.text
        assert "must accept exactly ('name',)" in caplog.text


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
    def test_component_field_collects_view(self, qapp: QApplication) -> None:

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

        app = app.build()
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

    def test_from_config_without_config_field_raises_on_construction(self) -> None:
        # declaring is legal: a base exists to be subclassed, and the subclass
        # is where `config` is named
        class TestApp(AppContainer):
            motor = declare_device(MyMotor, from_config="motor")

        with pytest.raises(TypeError, match="no config path was provided"):
            TestApp()

    def test_a_subclass_resolves_inherited_fields_against_its_own_config(
        self, config_path: Path
    ) -> None:
        class Base(AppContainer):
            motor = declare_device(MyMotor, from_config="motor")

        class Derived(Base, config=config_path / "mock_component_config.yaml"):
            pass

        assert Derived._device_components["motor"].kwargs["string"] == "from config"

    def test_two_subclasses_read_their_own_configs(self, config_path: Path) -> None:
        class Base(AppContainer):
            ctrl = declare_presenter(MockController, from_config="ctrl")

        class First(Base, config=config_path / "mock_component_config.yaml"):
            pass

        class Second(Base, config=config_path / "mock_component_alt_config.yaml"):
            pass

        assert First._presenter_components["ctrl"].kwargs["string"] == "config ctrl"
        assert Second._presenter_components["ctrl"].kwargs["string"] == "alt ctrl"

    def test_config_files_layer_in_order(self, config_path: Path) -> None:
        class TestApp(
            AppContainer,
            config=[
                config_path / "mock_common_config.yaml",
                config_path / "mock_overlay_config.yaml",
            ],
        ):
            ctrl = declare_presenter(MockController, from_config="ctrl")

        # the overlay adds a component and leaves the one it does not name
        assert TestApp._presenter_components["ctrl"].kwargs["string"] == "common ctrl"
        assert TestApp().config["name"] == "mock-overlay-session"

    def test_a_subclass_layers_its_config_over_its_base(
        self, config_path: Path
    ) -> None:
        class Base(AppContainer, config=config_path / "mock_common_config.yaml"):
            ctrl = declare_presenter(MockController, from_config="ctrl")

        class Derived(Base, config=config_path / "mock_overlay_config.yaml"):
            pass

        assert Base._presenter_components["ctrl"].kwargs["string"] == "common ctrl"
        assert Derived._presenter_components["ctrl"].kwargs["string"] == "common ctrl"
        assert Derived().config["name"] == "mock-overlay-session"

    def test_required_keys_are_checked_on_the_merged_configuration(
        self, config_path: Path
    ) -> None:
        # the overlay alone carries neither schema_version nor frontend
        with pytest.raises(KeyError, match="missing required keys"):

            class Alone(AppContainer, config=config_path / "mock_overlay_config.yaml"):
                ctrl = declare_presenter(MockController, from_config="ctrl")

    def test_layered_files_must_agree_on_the_frontend(self, config_path: Path) -> None:
        with pytest.raises(ValueError, match="contradicts"):

            class TestApp(
                AppContainer,
                config=[
                    config_path / "mock_common_config.yaml",
                    config_path / "mock_conflicting_config.yaml",
                ],
            ):
                ctrl = declare_presenter(MockController, from_config="ctrl")

    def test_layered_files_may_restate_an_agreeing_identity_key(
        self, config_path: Path
    ) -> None:
        # only a *different* value is refused; repeating one is legal
        class TestApp(
            AppContainer,
            config=[
                config_path / "mock_common_config.yaml",
                config_path / "mock_component_config.yaml",
            ],
        ):
            ctrl = declare_presenter(MockController, from_config="ctrl")

        assert TestApp().config["frontend"] == "pyqt"

    def test_a_component_named_in_both_files_is_taken_from_the_later_one(
        self, config_path: Path
    ) -> None:
        class TestApp(
            AppContainer,
            config=[
                config_path / "mock_common_config.yaml",
                config_path / "mock_component_config.yaml",
            ],
        ):
            ctrl = declare_presenter(MockController, from_config="ctrl")

        # a component entry is a constructor call, so the later file owns it
        # whole rather than contributing keys to it
        assert TestApp._presenter_components["ctrl"].kwargs == {
            "string": "config ctrl",
            "integer": 10,
            "floating": 2.0,
            "boolean": True,
        }

    def test_a_component_only_one_file_names_survives(self, config_path: Path) -> None:
        class TestApp(
            AppContainer,
            config=[
                config_path / "mock_common_config.yaml",
                config_path / "mock_overlay_config.yaml",
            ],
        ):
            ctrl = declare_presenter(MockController, from_config="ctrl")
            other = declare_presenter(MockController, from_config="other")

        assert TestApp._presenter_components["ctrl"].kwargs["string"] == "common ctrl"
        assert TestApp._presenter_components["other"].kwargs["string"] == "overlay only"

    def test_config_files_come_from_every_base(self, config_path: Path) -> None:
        class First(AppContainer, config=config_path / "mock_common_config.yaml"):
            pass

        class Second(AppContainer, config=config_path / "mock_overlay_config.yaml"):
            pass

        class Both(First, Second):
            ctrl = declare_presenter(MockController, from_config="ctrl")
            other = declare_presenter(MockController, from_config="other")

        assert len(Both._config_paths) == 2
        assert Both._presenter_components["ctrl"].kwargs["string"] == "common ctrl"
        assert Both._presenter_components["other"].kwargs["string"] == "overlay only"

    def test_a_file_reached_twice_is_read_once(self, config_path: Path) -> None:
        class Base(AppContainer, config=config_path / "mock_common_config.yaml"):
            pass

        class Derived(Base, config=config_path / "mock_common_config.yaml"):
            pass

        assert Derived._config_paths == Base._config_paths

    def test_a_section_written_empty_is_no_section(self, config_path: Path) -> None:
        # `presenters:` with nothing under it parses as None, not as {}
        class TestApp(
            AppContainer, config=config_path / "mock_empty_section_config.yaml"
        ):
            ctrl = declare_presenter(MockController, from_config="ctrl")

        assert TestApp._presenter_components["ctrl"].kwargs == {}

    @pytest.mark.parametrize(
        ("declare", "registry", "expected"),
        [
            (
                lambda: declare_device(MyMotor, from_config="motor"),
                "_device_components",
                {"egu": "um"},
            ),
            (
                lambda: declare_view(MockQtView, from_config="widget"),
                "_view_components",
                {"label": "overlay widget"},
            ),
        ],
        ids=["device", "view"],
    )
    def test_every_layer_replaces_a_component_it_names(
        self,
        config_path: Path,
        declare: Callable[[], Any],
        registry: str,
        expected: dict[str, Any],
    ) -> None:
        # the same rule the presenter case pins, for the other two layers: the
        # later file owns the entry, so nothing from the file underneath leaks in
        class TestApp(
            AppContainer,
            config=[
                config_path / "mock_common_config.yaml",
                config_path / "mock_overlay_config.yaml",
            ],
        ):
            component = declare()

        assert getattr(TestApp, registry)["component"].kwargs == expected

    @pytest.mark.parametrize(
        ("declare", "registry", "name"),
        [
            (
                lambda: declare_device(MyMotor, from_config="other_motor"),
                "_device_components",
                "other_motor",
            ),
            (
                lambda: declare_view(MockQtView, from_config="other_widget"),
                "_view_components",
                "other_widget",
            ),
        ],
        ids=["device", "view"],
    )
    def test_every_layer_adds_a_component_only_it_names(
        self,
        config_path: Path,
        declare: Callable[[], Any],
        registry: str,
        name: str,
    ) -> None:
        class TestApp(
            AppContainer,
            config=[
                config_path / "mock_common_config.yaml",
                config_path / "mock_overlay_config.yaml",
            ],
        ):
            component = declare()

        kwargs = getattr(TestApp, registry)["component"].kwargs
        assert kwargs["string" if "motor" in name else "label"] == "overlay only"

    def test_a_component_only_the_lower_file_names_survives_in_every_layer(
        self, config_path: Path
    ) -> None:
        class TestApp(
            AppContainer,
            config=[
                config_path / "mock_common_config.yaml",
                config_path / "mock_overlay_config.yaml",
            ],
        ):
            motor = declare_device(MyMotor, from_config="motor")
            ctrl = declare_presenter(MockController, from_config="ctrl")

        # the overlay names `motor` and not `ctrl`
        assert TestApp._device_components["motor"].kwargs == {"egu": "um"}
        assert TestApp._presenter_components["ctrl"].kwargs["string"] == "common ctrl"

    def test_the_layer_chain_is_logged(
        self, config_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="redsun"):

            class TestApp(
                AppContainer,
                config=[
                    config_path / "mock_common_config.yaml",
                    config_path / "mock_overlay_config.yaml",
                ],
            ):
                motor = declare_device(MyMotor, from_config="motor")

        assert "Reading configuration from 2 sources" in caplog.text
        assert "mock_common_config.yaml" in caplog.text
        assert "mock_overlay_config.yaml" in caplog.text

    def test_a_shadowed_component_is_logged(
        self, config_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="redsun"):

            class TestApp(
                AppContainer,
                config=[
                    config_path / "mock_common_config.yaml",
                    config_path / "mock_overlay_config.yaml",
                ],
            ):
                motor = declare_device(MyMotor, from_config="motor")

        # `motor` is named in both files, `ctrl` in only one
        assert "Component 'motor' in 'devices'" in caplog.text
        assert "Component 'ctrl'" not in caplog.text

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
    """Tests for the boundary between the two configuration schemas."""

    def test_redsun_config_no_component_fields(self) -> None:
        """RedSunConfig must not expose devices/presenters/views."""
        assert "devices" not in RedSunConfig.__annotations__
        assert "presenters" not in RedSunConfig.__annotations__
        assert "views" not in RedSunConfig.__annotations__


class TestLogLevel:
    """Tests for the level the ``redsun`` logger runs at."""

    @pytest.fixture(autouse=True)
    def _restore_level(self) -> Iterator[None]:
        logger = logging.getLogger("redsun")
        level = logger.level
        yield
        logger.setLevel(level)

    def test_a_container_leaves_the_level_alone_by_default(self) -> None:
        logging.getLogger("redsun").setLevel(logging.WARNING)

        AppContainer()

        assert logging.getLogger("redsun").level == logging.WARNING

    @pytest.mark.parametrize(
        ("level", "expected"),
        [
            pytest.param(logging.DEBUG, logging.DEBUG, id="constant"),
            pytest.param("DEBUG", logging.DEBUG, id="name"),
            pytest.param("debug", logging.DEBUG, id="lowercase-name"),
            pytest.param(logging.WARNING, logging.WARNING, id="another-constant"),
        ],
    )
    def test_a_keyword_sets_the_level(self, level: int | str, expected: int) -> None:
        AppContainer(log_level=level)

        assert logging.getLogger("redsun").level == expected

    @pytest.mark.parametrize(
        ("level", "error"),
        [
            pytest.param("verbose", ValueError, id="not-a-level"),
            pytest.param(3.5, TypeError, id="not-a-level-at-all"),
        ],
    )
    def test_a_level_naming_nothing_is_refused(
        self, level: Any, error: type[Exception]
    ) -> None:
        logging.getLogger("redsun").setLevel(logging.WARNING)

        with pytest.raises(error):
            AppContainer(log_level=level)

        assert logging.getLogger("redsun").level == logging.WARNING

    def test_from_config_passes_the_level_on(
        self, mock_entry_points: None, config_path: Path
    ) -> None:
        logging.getLogger("redsun").setLevel(logging.WARNING)

        AppContainer.from_config(
            str(config_path / "mock_motor_config.yaml"), log_level=logging.DEBUG
        )

        assert logging.getLogger("redsun").level == logging.DEBUG


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

        built = app.build()

        assert built._qt_app is not None
        assert QApplication.instance() is built._qt_app
        assert built.is_built
        assert "motor" in built.devices
        assert "v" in built.views

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
        assert isinstance(parent, MotorWithChild)
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

        def patched_run(self: AppContainer) -> None:
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

            def connect_devices(self, mock: bool = False) -> None:
                connect_calls.append("called")
                super().connect_devices(mock=mock)

        app = TrackingApp()
        app.build()
        app.connect_devices(mock=True)
        assert connect_calls == ["called"]

        # Simulate run() when already connected - connect_devices must not fire again.
        if not app._devices_connected:
            app.connect_devices(mock=True)

        assert connect_calls == ["called"]  # still only one call


class TestBuiltinPlugins:
    """Builtin components resolve through the real ``redsun.plugins`` entry point.

    No ``mock_entry_points`` fixture here: the point is that the installed
    redsun distribution itself advertises ``plugins.yaml``, so a user config
    can reference ``plugin_name: redsun`` with zero extra setup.
    """

    def test_from_config_builtin_storage_presenter(self, tmp_path: Path) -> None:
        config = {
            "schema_version": 1.0,
            "frontend": "pyqt",
            "name": "builtin-session",
            "presenters": {
                "storage": {
                    "plugin_name": "redsun",
                    "plugin_id": "storage",
                    "base_dir": str(tmp_path),
                }
            },
        }
        cfg_file = tmp_path / "builtin.yaml"
        cfg_file.write_text(yaml.dump(config))

        container = AppContainer.from_config(str(cfg_file))
        container.build()

        assert "storage" in container.presenters
        presenter = container.presenters["storage"]
        assert isinstance(presenter, StoragePresenter)
        # the provider is session-scoped from the config and DI-exposed
        provider = container.virtual_container.require(PATH_PROVIDER)
        assert provider is presenter.path_provider
        assert "builtin-session" in provider().directory_path.parts


class TestProtocolValidationAtBuild:
    """Protocol compliance is validated on built instances, not classes.

    Class-level checks cannot see attributes assigned in ``__init__`` - the old hasattr-on-class screen rejected exactly these implementers.
    """

    def test_structural_presenter_without_abc_builds(self) -> None:
        class DuckPresenter:
            def __init__(self, name: str, devices: dict[str, Device], /) -> None:
                self.name = name
                self.devices = devices

        comp = _PresenterComponent(DuckPresenter, "duck")
        instance = comp.build({})
        assert isinstance(instance, PPresenter)

    def test_non_compliant_presenter_raises_at_build(self) -> None:
        class NotAPresenter:
            def __init__(self, name: str, devices: dict[str, Device], /) -> None:
                pass  # stores neither name nor devices

        # the arg-type ignore is the point: mypy already rejects this class,
        # the runtime check protects callers without static typing
        comp = _PresenterComponent(NotAPresenter, "bad")  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="'devices' is missing"):
            comp.build({})

    def test_structural_view_without_qt_builds(self) -> None:
        class HeadlessView:
            def __init__(self, name: str, /) -> None:
                self.name = name
                self.view_position = ViewPosition.CENTER

        comp = _ViewComponent(HeadlessView, "headless")
        assert isinstance(comp.build(), PView)

    def test_non_compliant_view_raises_at_build(self) -> None:
        class NotAView:
            def __init__(self, name: str, /) -> None:
                self.name = name  # missing view_position

        # the arg-type ignore is the point: mypy already rejects this class,
        # the runtime check protects callers without static typing
        comp = _ViewComponent(NotAView, "bad")  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="'view_position' is missing"):
            comp.build()


class TestConstructorSignatureGate:
    """Class-level gate: constructor positional shape checked via inspect.

    The classes below all satisfy the protocols at instance level, so these
    tests isolate the signature gate from the build-time protocol gate.
    """

    def test_presenter_wrong_positional_names_rejected(self) -> None:
        class WrongNames:
            def __init__(self, identifier: str, devices: dict[str, Device], /) -> None:
                self.name = identifier
                self.devices = devices

        with pytest.raises(TypeError, match="leading positional"):
            _PresenterComponent(WrongNames, "bad")

    def test_presenter_extra_required_positional_rejected(self) -> None:
        class ExtraPositional:
            def __init__(
                self, name: str, devices: dict[str, Device], extra: int, /
            ) -> None:
                self.name = name
                self.devices = devices

        with pytest.raises(TypeError, match="leading positional"):
            _PresenterComponent(ExtraPositional, "bad")

    def test_presenter_var_positional_rejected(self) -> None:
        class VarArgs:
            def __init__(self, *args: Any) -> None:
                self.name = "x"
                self.devices: dict[str, Device] = {}

        with pytest.raises(TypeError, match="leading positional"):
            _PresenterComponent(VarArgs, "bad")

    def test_presenter_optional_trailing_params_accepted(self) -> None:
        """StoragePresenter-shaped signatures pass: defaults after the slash."""

        class Configurable:
            def __init__(
                self,
                name: str,
                devices: dict[str, Device],
                /,
                base_dir: str | None = None,
                **kwargs: Any,
            ) -> None:
                self.name = name
                self.devices = devices

        comp = _PresenterComponent(Configurable, "ok", base_dir="/tmp")
        assert isinstance(comp.build({}), PPresenter)

    def test_view_extra_positional_rejected(self) -> None:
        class TwoPositionals:
            def __init__(self, name: str, devices: dict[str, Device], /) -> None:
                self.name = name
                self.view_position = ViewPosition.CENTER

        with pytest.raises(TypeError, match="leading positional"):
            _ViewComponent(TwoPositionals, "bad")

    def test_view_name_only_accepted(self) -> None:
        class Minimal:
            def __init__(self, name: str, /) -> None:
                self.name = name
                self.view_position = ViewPosition.CENTER

        comp = _ViewComponent(Minimal, "ok")
        assert isinstance(comp.build(), PView)


class _WiredApp(AppContainer):
    """Connects a marked slot; the components are named in code, so typed."""

    motor = declare_device(MyMotor, egu="mm", string="s")
    mover = declare_presenter(AsyncMotorController)
    ctrl = declare_presenter(MockController)

    def wire(self) -> None:
        self.connect(self.mover.sig_motor_moved, self.ctrl.on_motor_moved)


class _UnmarkedSlotApp(AppContainer):
    """Targets a real method that was never marked with ``slot``."""

    mover = declare_presenter(AsyncMotorController)
    ctrl = declare_presenter(MockController)

    def wire(self) -> None:
        self.connect(self.mover.sig_motor_moved, self.ctrl.not_connectable)


class _MismatchedSlotApp(AppContainer):
    """Targets a marked slot that takes more arguments than the signal emits."""

    mover = declare_presenter(AsyncMotorController)
    ctrl = declare_presenter(MockController)

    def wire(self) -> None:
        self.connect(self.mover.sig_motor_moved, self.ctrl.on_too_many)


class _PartlyBuiltApp(AppContainer):
    """Names a presenter that cannot build, alongside two that can."""

    mover = declare_presenter(AsyncMotorController)
    ctrl = declare_presenter(MockController)
    broken = declare_presenter(BrokenController)

    def wire(self) -> None:
        self.connect(self.broken.sig_motor_moved, self.ctrl.on_motor_moved)
        self.connect(self.mover.sig_motor_moved, self.ctrl.on_motor_moved)


class _TypoApp(AppContainer):
    """Names a port that the presenter it belongs to does not have."""

    mover = declare_presenter(AsyncMotorController)
    ctrl = declare_presenter(MockController)

    def wire(self) -> None:
        # the ignore is the point: mypy already rejects the typo, and the
        # runtime failure is what protects a container without static typing
        self.connect(self.mover.sig_typo, self.ctrl.on_motor_moved)  # type: ignore[attr-defined]


class _PartlyBuiltViewApp(AppContainer):
    """Wires a view that cannot build and one that can."""

    mover = declare_presenter(AsyncMotorController)
    ok = declare_view(MockMotorView)
    bad = declare_view(BrokenView)

    def wire(self) -> None:
        self.connect(self.mover.sig_motor_moved, self.bad.note_position)
        self.connect(self.mover.sig_motor_moved, self.ok.note_position)


class TestWiring:
    """Tests for the ``wire`` hook and the connections it records."""

    @pytest.fixture
    def app(self) -> Iterator[_WiredApp]:
        built = _WiredApp().build()
        yield built
        if built.is_built:
            built.shutdown()

    def test_declared_connection_is_live_after_build(self, app: _WiredApp) -> None:
        """A component attribute resolves to its built instance during wiring."""
        app.mover.sig_motor_moved.emit("motor", 1.0)

        assert app.ctrl.moved == [("motor", 1.0)]

    def test_connection_is_recorded_with_both_port_paths(self, app: _WiredApp) -> None:
        """The link names the components by the keys the container knows."""
        assert [str(link) for link in app.virtual_container.connections] == [
            "mover.sig_motor_moved -> ctrl.on_motor_moved"
        ]

    def test_shutdown_disconnects(self, app: _WiredApp) -> None:
        """Teardown drops the links the container made."""
        # read before shutdown: a shut-down container owns no component
        mover, ctrl = app.mover, app.ctrl
        app.shutdown()

        mover.sig_motor_moved.emit("motor", 1.0)

        assert ctrl.moved == []
        assert app.virtual_container.connections == []

    def test_a_connection_naming_a_failed_component_is_skipped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The rest of ``wire`` runs, and the link that was dropped is reported."""
        with caplog.at_level(logging.WARNING, logger="redsun"):
            app = _PartlyBuiltApp().build()

        app.mover.sig_motor_moved.emit("motor", 1.0)

        assert app.ctrl.moved == [("motor", 1.0)]
        assert [str(link) for link in app.virtual_container.connections] == [
            "mover.sig_motor_moved -> ctrl.on_motor_moved"
        ]
        assert any(
            "broken" in record.message and record.levelno == logging.WARNING
            for record in caplog.records
        )
        app.shutdown()

    def test_a_shut_down_container_gives_the_declaration_again(self) -> None:
        """The stand-in lasts as long as the build that produced it."""
        app = _PartlyBuiltApp().build()
        app.shutdown()

        assert isinstance(app.broken, _PresenterComponent)

    def test_a_port_a_built_component_lacks_still_fails_the_build(self) -> None:
        """Only a component that failed is absorbed, so a typo is still an error."""
        with pytest.raises(AttributeError, match="sig_typo"):
            _TypoApp().build()

    @pytest.mark.qt
    def test_a_failed_view_leaves_the_widgets_of_the_views_that_built(
        self, qapp: QApplication
    ) -> None:
        """A build that returns instead of raising keeps what it made."""
        before = len(QApplication.topLevelWidgets())

        app = _PartlyBuiltViewApp().build()

        assert len(QApplication.topLevelWidgets()) == before + 1
        assert [str(link) for link in app.virtual_container.connections] == [
            "mover.sig_motor_moved -> ok.note_position  [thread=main]"
        ]
        app.shutdown()

    def test_connecting_an_unmarked_method_fails_the_build(self) -> None:
        """Only a marked method is connectable, so a typo cannot pass silently."""
        with pytest.raises(WiringError, match="not connectable"):
            _UnmarkedSlotApp().build()

    def test_incompatible_slot_names_both_ends(self) -> None:
        """A signature mismatch is a build error naming the two ports."""
        with pytest.raises(
            WiringError, match="mover.sig_motor_moved -> ctrl.on_too_many"
        ):
            _MismatchedSlotApp().build()


class TestYamlWiring:
    """Tests for the ``wiring`` section of a configuration file."""

    def _build(self, config_path: Path, mock_entry_points: None) -> AppContainer:
        return AppContainer.from_config(
            str(config_path / "mock_wiring_config.yaml")
        ).build()

    def test_declared_links_are_live(
        self, mock_entry_points: None, config_path: Path
    ) -> None:
        """A rule in the file connects the same ports the Python form would."""
        app = self._build(config_path, mock_entry_points)
        mover = component(app.presenters, "mover", AsyncMotorController)
        ctrl = component(app.presenters, "ctrl", MockController)

        mover.sig_motor_moved.emit("motor", 1.0)

        assert ctrl.moved == [("motor", 1.0)]

    def test_signal_group_members_are_addressed_by_member_name(
        self, mock_entry_points: None, config_path: Path
    ) -> None:
        """``component.member`` reaches a signal declared inside a group."""
        app = self._build(config_path, mock_entry_points)
        grouped = component(app.presenters, "grouped", GroupedController)

        grouped.frames.median.emit("a")
        grouped.frames.filtered.emit("b")

        assert grouped.seen == ["a", "b"]

    def test_the_whole_graph_is_recorded(
        self, mock_entry_points: None, config_path: Path
    ) -> None:
        """Every rule appears in the report, named by its port path."""
        app = self._build(config_path, mock_entry_points)

        assert sorted(str(link) for link in app.virtual_container.connections) == [
            "grouped.filtered -> grouped.absorb",
            "grouped.median -> grouped.absorb",
            "mover.sig_motor_moved -> ctrl.on_motor_moved",
        ]

    def test_wire_runs_before_the_configuration_section(
        self, mock_entry_points: None, config_path: Path
    ) -> None:
        """A container may declare connections in code and in the file."""
        app = AppContainer.from_config(str(config_path / "mock_wiring_config.yaml"))
        grouped_link: list[str] = []

        def wire(self: AppContainer) -> None:
            grouped_link.append("wire")

        type(app).wire = wire  # type: ignore[method-assign]
        app.build()

        assert grouped_link == ["wire"]
        assert len(app.virtual_container.connections) == 3

    @pytest.mark.parametrize(
        ("rule", "expected"),
        [
            (
                {"from": "nope.sig_motor_moved", "to": "ctrl.on_motor_moved"},
                "was not built",
            ),
            (
                {"from": "mover.sig_typo", "to": "ctrl.on_motor_moved"},
                "exposes no signal",
            ),
            ({"from": "mover.sig_motor_moved", "to": "ctrl.typo"}, "exposes no slot"),
            (
                {"from": "mover.sig_motor_moved", "to": "ctrl.not_connectable"},
                "exposes no slot",
            ),
            ({"from": "mover", "to": "ctrl.on_motor_moved"}, "is not a port path"),
            ({"from": "mover.sig_motor_moved"}, "keys 'from' and 'to'"),
        ],
    )
    def test_a_bad_rule_fails_the_build(
        self,
        rule: dict[str, str],
        expected: str,
        mock_entry_points: None,
        config_path: Path,
        tmp_path: Path,
    ) -> None:
        """Every way of getting a rule wrong names the offending path."""
        source = yaml.safe_load((config_path / "mock_wiring_config.yaml").read_text())
        source["wiring"] = [rule]
        broken = tmp_path / "broken_wiring.yaml"
        broken.write_text(yaml.safe_dump(source))

        with pytest.raises(WiringError, match=expected):
            AppContainer.from_config(str(broken)).build()

    def test_a_rule_naming_a_component_that_failed_is_skipped(
        self,
        mock_entry_points: None,
        config_path: Path,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The build returns, having made every rule that names what it built.

        The rule it dropped is reported, so that a connection cannot go missing
        without a record of it.
        """
        source = yaml.safe_load((config_path / "mock_wiring_config.yaml").read_text())
        source["presenters"]["broken"] = {
            "plugin_name": "mock-pkg",
            "plugin_id": "broken_controller",
        }
        source["wiring"].append(
            {"from": "mover.sig_motor_moved", "to": "broken.on_motor_moved"}
        )
        tolerated = tmp_path / "tolerated_wiring.yaml"
        tolerated.write_text(yaml.safe_dump(source))

        with caplog.at_level(logging.WARNING, logger="redsun"):
            app = AppContainer.from_config(str(tolerated)).build()

        assert "broken" not in app.presenters
        assert any(
            "broken.on_motor_moved" in record.message
            and record.levelno == logging.WARNING
            for record in caplog.records
        )
        assert sorted(str(link) for link in app.virtual_container.connections) == [
            "grouped.filtered -> grouped.absorb",
            "grouped.median -> grouped.absorb",
            "mover.sig_motor_moved -> ctrl.on_motor_moved",
        ]

    def test_an_unmarked_method_is_not_a_slot_port(
        self, mock_entry_points: None, config_path: Path
    ) -> None:
        """A method exists but is not addressable until it is marked."""
        app = self._build(config_path, mock_entry_points)
        surface = ports(app.presenters["ctrl"])

        assert "on_motor_moved" in surface.slots
        assert "not_connectable" not in surface.slots
