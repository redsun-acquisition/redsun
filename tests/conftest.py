import pytest
from unittest.mock import MagicMock

from typing import Callable
from importlib.metadata import EntryPoint
from pathlib import Path

from mocks import MockMotor, MockMotorInfo

@pytest.fixture
def config_path() -> Path:
    return Path(__file__).parent / "mocks" / "configs"

@pytest.fixture
def mock_motor_entry_points() -> Callable[[str], list[EntryPoint]]:

    def mocked_motor_entry_points(group: str) -> list[EntryPoint]:
        plugins = []

        if group == "redsun.plugins.motors.config":
            info_ep = EntryPoint(
            name="motor",
            value="mock_motor:MockMotorInfo",
            group="redsun.plugins.motors.config",
            )
            info_ep.load = MagicMock(return_value=MockMotorInfo) # type: ignore
            plugins.append(info_ep)

        if group == "redsun.plugins.motors":
            model_ep = EntryPoint(
                name="motor", 
                value="mock_motor:MockMotor", 
                group="redsun.plugins.motors"
            )
            model_ep.load = MagicMock(return_value=MockMotor) # type: ignore
            plugins.append(model_ep)

        return plugins
    
    return mocked_motor_entry_points
