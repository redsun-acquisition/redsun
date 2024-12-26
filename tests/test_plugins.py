# type: ignore

from unittest.mock import MagicMock, patch

import logging
from pathlib import Path
from importlib.metadata import EntryPoint
from typing import Callable
from redsun.controller.plugins import PluginManager
from sunflare.config import RedSunInstanceInfo

from mocks import MockMotor, MockMotorInfo

logging.basicConfig(level=logging.DEBUG)

def test_load_motor_plugins(config_path: Path, mock_motor_entry_points: Callable[[str], list[EntryPoint]]) -> None:
    # Create a mock that returns our function
    mock_ep = MagicMock(side_effect=mock_motor_entry_points)

    # Need to patch where entry_points is imported, not where it's defined
    with patch('redsun.controller.plugins.entry_points', mock_ep):

        # Then test through the plugin manager
        config, types_groups, _ = PluginManager.load_configuration(str(config_path / "mock_motor_config.yaml"))

        assert isinstance(config, RedSunInstanceInfo)
        assert len(types_groups["motors"]) == 2
        assert ["Single axis motor", "Double axis motor"] == list(types_groups["motors"].keys())

        # check config for single axis motor
        assert config.motors["Single axis motor"].model_name == "MockMotor"
        assert config.motors["Single axis motor"].axes == ["X"]
        assert config.motors["Single axis motor"].integer == 42
        assert config.motors["Single axis motor"].floating == 3.14
        assert config.motors["Single axis motor"].string == "Hello, World!"

        # check config for double axis motor
        assert config.motors["Double axis motor"].model_name == "MockMotor"
        assert config.motors["Double axis motor"].axes == ["X", "Y"]
        assert config.motors["Double axis motor"].step_egu == "mm"
        assert config.motors["Double axis motor"].integer == 314
        assert config.motors["Double axis motor"].floating == 4.2
        assert config.motors["Double axis motor"].string == "Goodbye, World!"
