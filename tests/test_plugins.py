# type: ignore
import pytest

from unittest.mock import MagicMock, patch

import logging
from pathlib import Path
from importlib.metadata import EntryPoint
from typing import Callable
from redsun.controller.plugins import PluginManager
from sunflare.config import RedSunSessionInfo

from mocks import (
    mocked_motor_missing_entry_points, 
    mocked_motor_mismatched_entry_points, 
    mocked_motor_non_derived_info_entry_points,
    mocked_ctrl_non_derived_info_entry_points,
    mocked_ctrl_non_derived_entry_points,
    mocked_ctrl_mismatched_entry_points
)

logging.basicConfig(level=logging.DEBUG)

def test_load_motor_plugins(config_path: Path, mock_motor_entry_points: Callable[[str], list[EntryPoint]]) -> None:
    # Create a mock that returns our function
    mock_ep = MagicMock(side_effect=mock_motor_entry_points)

    # Need to patch where entry_points is imported, not where it's defined
    with patch('redsun.controller.plugins.entry_points', mock_ep):

        # Then test through the plugin manager
        config, types_groups, _ = PluginManager.load_configuration(str(config_path / "mock_motor_config.yaml"))

        assert isinstance(config, RedSunSessionInfo)
        assert len(types_groups["motors"]) == 2
        assert ["Single axis motor", "Double axis motor"] == list(types_groups["motors"].keys())

        # check config for single axis motor
        assert config.models["Single axis motor"].model_name == "MockMotor"
        assert config.models["Single axis motor"].axes == ["X"]
        assert config.models["Single axis motor"].integer == 42
        assert config.models["Single axis motor"].floating == 3.14
        assert config.models["Single axis motor"].string == "Hello, World!"

        # check config for double axis motor
        assert config.models["Double axis motor"].model_name == "MockMotor"
        assert config.models["Double axis motor"].axes == ["X", "Y"]
        assert config.models["Double axis motor"].step_egu == "mm"
        assert config.models["Double axis motor"].integer == 314
        assert config.models["Double axis motor"].floating == 4.2
        assert config.models["Double axis motor"].string == "Goodbye, World!"

def test_load_detector_plugins(config_path: Path, mock_detector_entry_points: Callable[[str], list[EntryPoint]]) -> None:
    # Create a mock that returns our function
    mock_ep = MagicMock(side_effect=mock_detector_entry_points)

    # Need to patch where entry_points is imported, not where it's defined
    with patch('redsun.controller.plugins.entry_points', mock_ep):

        # Then test through the plugin manager
        config, types_groups, _ = PluginManager.load_configuration(str(config_path / "mock_detector_config.yaml"))

        assert isinstance(config, RedSunSessionInfo)
        assert len(config.models) == 2
        assert len(types_groups["detectors"]) == 2
        assert ["iSCAT channel", "TIRF channel"] == list(types_groups["detectors"].keys())

def test_load_controller_plugins(config_path: Path, mock_controller_entry_points: Callable[[str], list[EntryPoint]]) -> None:
    # Create a mock that returns our function
    mock_ep = MagicMock(side_effect=mock_controller_entry_points)

    # Need to patch where entry_points is imported, not where it's defined
    with patch('redsun.controller.plugins.entry_points', mock_ep):

        # Then test through the plugin manager
        config, types_groups, _ = PluginManager.load_configuration(str(config_path / "mock_controller_config.yaml"))

        assert isinstance(config, RedSunSessionInfo)
        assert len(config.controllers) == 1
        assert len(config.models) == 0
        assert len(types_groups["controllers"]) == 1
        assert ["Mock Controller"] == list(types_groups["controllers"].keys())

mocked_error_entry_points = [
    mocked_motor_mismatched_entry_points,
    mocked_motor_missing_entry_points,
    mocked_motor_non_derived_info_entry_points,
    mocked_ctrl_non_derived_info_entry_points,
    mocked_ctrl_non_derived_entry_points,
    mocked_ctrl_mismatched_entry_points
]

@pytest.mark.parametrize("mock_entry_points", mocked_error_entry_points)
def test_errors_plugin_loading(config_path: Path, mock_entry_points: Callable[[str], list[EntryPoint]]) -> None:
    # Create a mock that returns our function
    mock_ep = MagicMock(side_effect=mock_entry_points)

    # Need to patch where entry_points is imported, not where it's defined
    with patch('redsun.controller.plugins.entry_points', mock_ep):
        config, types_groups, _ = PluginManager.load_configuration(str(config_path / "mock_motor_config.yaml"))
        assert config.motors == {}
        assert len(types_groups["motors"]) == 0
