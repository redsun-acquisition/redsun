import pytest
from unittest.mock import MagicMock

from typing import Callable
from importlib.metadata import EntryPoint
from pathlib import Path

from mocks import (
    MockMotor, 
    MockMotorInfo, 
    MockDetector, 
    MockDetectorInfo,
    MockController,
    MockControllerInfo,
)

@pytest.fixture
def config_path() -> Path:
    return Path(__file__).parent / "mocks" / "configs"

@pytest.fixture
def mock_detector_entry_points() -> Callable[[str], list[EntryPoint]]:

    def mocked_detector_entry_points(group: str) -> list[EntryPoint]:
        plugins = []

        if group == "redsun.plugins.models.config":
            info_ep = EntryPoint(
                name="detector",
                value="mock_detector:MockDetectorInfo",
                group="redsun.plugins.models.config",
            )
            object.__setattr__(info_ep, "load", MagicMock(return_value=MockDetectorInfo))
            plugins.append(info_ep)

        if group == "redsun.plugins.models":
            model_ep = EntryPoint(
                name="detector",
                value="mock_detector:MockDetector",
                group="redsun.plugins.models",
            )
            object.__setattr__(model_ep, "load", MagicMock(return_value=MockDetector))
            plugins.append(model_ep)

        return plugins
    
    return mocked_detector_entry_points

@pytest.fixture
def mock_motor_entry_points() -> Callable[[str], list[EntryPoint]]:

    def mocked_motor_entry_points(group: str) -> list[EntryPoint]:
        plugins = []

        if group == "redsun.plugins.models.config":
            info_ep = EntryPoint(
                name="motor",
                value="mock_motor:MockMotorInfo",
                group="redsun.plugins.models.config",
            )
            object.__setattr__(info_ep, "load", MagicMock(return_value=MockMotorInfo))
            plugins.append(info_ep)

        if group == "redsun.plugins.models":
            model_ep = EntryPoint(
                name="motor", 
                value="mock_motor:MockMotor", 
                group="redsun.plugins.models"
            )
            object.__setattr__(model_ep, "load", MagicMock(return_value=MockMotor))
            plugins.append(model_ep)

        return plugins
    
    return mocked_motor_entry_points

@pytest.fixture
def mock_controller_entry_points() -> Callable[[str], list[EntryPoint]]:

    def mocked_controller_entry_points(group: str) -> list[EntryPoint]:
        plugins = []

        if group == "redsun.plugins.controllers.config":
            info_ep = EntryPoint(
                name="controller",
                value="mock_controller:MockControllerInfo",
                group="redsun.plugins.controllers.config",
            )
            object.__setattr__(info_ep, "load", MagicMock(return_value=MockControllerInfo))
            plugins.append(info_ep)
        if group == "redsun.plugins.controllers":
            model_ep = EntryPoint(
                name="controller",
                value="mock_controller:MockController",
                group="redsun.plugins.controllers",
            )
            object.__setattr__(model_ep, "load", MagicMock(return_value=MockController))
            plugins.append(model_ep)
        
        return plugins
    return mocked_controller_entry_points
