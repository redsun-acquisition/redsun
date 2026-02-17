"""Tests for plugin discovery and loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from redsun.plugins import (
    _check_device_protocol,
    _check_presenter_protocol,
    _check_view_protocol,
    load_configuration,
)


class TestPluginLoading:
    """Tests for loading plugin classes from manifests."""

    def test_load_motor_config(
        self, mock_entry_points: Any, config_path: Path
    ) -> None:
        config, types = load_configuration(str(config_path / "mock_motor_config.yaml"))

        assert len(types["devices"]) == 2
        assert "Single axis motor" in types["devices"]
        assert "Double axis motor" in types["devices"]
        assert len(types["presenters"]) == 0
        assert len(types["views"]) == 0

    def test_load_detector_config(
        self, mock_entry_points: Any, config_path: Path
    ) -> None:
        config, types = load_configuration(
            str(config_path / "mock_detector_config.yaml")
        )

        assert len(types["devices"]) == 2
        assert "iSCAT channel" in types["devices"]
        assert "TIRF channel" in types["devices"]

    def test_load_controller_config(
        self, mock_entry_points: Any, config_path: Path
    ) -> None:
        config, types = load_configuration(
            str(config_path / "mock_controller_config.yaml")
        )

        assert len(types["presenters"]) == 1
        assert "MockController" in types["presenters"]

        from mock_pkg.controller import MockController

        assert types["presenters"]["MockController"] is MockController

    def test_load_hidden_model_config(
        self, mock_entry_points: Any, config_path: Path
    ) -> None:
        config, types = load_configuration(
            str(config_path / "hidden_model_config.yaml")
        )

        assert len(types["devices"]) == 1

        from mock_pkg.device.hidden import HiddenModel

        assert types["devices"]["iSCAT channel"] is HiddenModel

    def test_broken_model_loads_valid_only(
        self, mock_entry_points: Any, config_path: Path
    ) -> None:
        """Broken device class still passes protocol check (inherits Device).

        The build step would fail, not the loading step.
        """
        config, types = load_configuration(
            str(config_path / "broken_model_config.yaml")
        )

        from mock_pkg.device import MockDetector

        assert types["devices"]["TIRF channel"] is MockDetector

    def test_config_returns_raw_dict(
        self, mock_entry_points: Any, config_path: Path
    ) -> None:
        config, _ = load_configuration(str(config_path / "mock_motor_config.yaml"))

        assert isinstance(config, dict)
        assert config["schema"] == "1.0"
        assert config["frontend"] == "pyqt"
        assert config["session"] == "mock-session"
        assert "devices" in config

    def test_full_config(
        self, mock_entry_points: Any, config_path: Path
    ) -> None:
        config, types = load_configuration(
            str(config_path / "mock_full_config.yaml")
        )

        assert len(types["devices"]) == 1
        assert len(types["presenters"]) == 1
        assert len(types["views"]) == 1


class TestProtocolChecks:
    """Tests for protocol validation helpers."""

    def test_device_protocol_derived(self) -> None:
        from mock_pkg.device import MyMotor

        assert _check_device_protocol(MyMotor) is True

    def test_device_protocol_non_derived(self) -> None:
        from mock_pkg.device import NonDerivedMotor

        assert _check_device_protocol(NonDerivedMotor) is True

    def test_presenter_protocol_derived(self) -> None:
        from mock_pkg.controller import MockController

        assert _check_presenter_protocol(MockController) is True

    def test_view_protocol_check(self) -> None:
        from mock_pkg.view import MockQtView

        assert _check_view_protocol(MockQtView) is True
