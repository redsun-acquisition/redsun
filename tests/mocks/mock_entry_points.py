"""Entry points used to test error conditions."""

import sys
from unittest.mock import MagicMock

from .mock_detector import *
from .mock_motor import *
from .mock_controller import *

if sys.version_info >= (3, 10):
    from importlib.metadata import EntryPoint
else:
    from importlib_metadata import EntryPoint

"""Motor defined without config entry point."""
def mocked_motor_missing_entry_points(group: str) -> list[EntryPoint]:
    plugins = []

    if group == "redsun.plugins.motors":
        model_ep = EntryPoint(
            name="motor",
            value="mock_motor:MockMotor",
            group="redsun.plugins.motors",
        )
        model_ep.load = MagicMock(return_value=MockMotor) # type: ignore
        plugins.append(model_ep)
    return plugins

def mocked_motor_mismatched_entry_points(group: str) -> list[EntryPoint]:
    plugins = []
    if group == "redsun.plugins.motors.config":
        info_ep = EntryPoint(
            name="motor_config",
            value="mock_motor:MockMotorInfo",
            group="redsun.plugins.motors.config",
        )
        plugins.append(info_ep)
    if group == "redsun.plugins.motors":
        model_ep = EntryPoint(
            name="motor",
            value="mock_motor:MockMotor",
            group="redsun.plugins.motors",
        )
        plugins.append(model_ep)
    return plugins

def mocked_motor_non_derived_info_entry_points(group: str) -> list[EntryPoint]:
    plugins = []
    if group == "redsun.plugins.motors.config":
        info_ep = EntryPoint(
            name="motor",
            value="mock_motor:NonDerivedDetectorInfo",
            group="redsun.plugins.motors.config",
        )
        info_ep.load = MagicMock(return_value=NonDerivedMotorInfo) # type: ignore
        plugins.append(info_ep)

    if group == "redsun.plugins.motors":
        model_ep = EntryPoint(
            name="motor",
            value="mock_motor:MockMotor",
            group="redsun.plugins.motors",
        )
        model_ep.load = MagicMock(return_value=MockMotor) # type: ignore
        plugins.append(model_ep)
    return plugins

def mocked_ctrl_mismatched_entry_points(group: str) -> list[EntryPoint]:
    plugins = []
    if group == "redsun.plugins.controllers.config":
        info_ep = EntryPoint(
            name="controller_config",
            value="mock_controller:MockControllerInfo",
            group="redsun.plugins.controllers.config",
        )
        plugins.append(info_ep)
    if group == "redsun.plugins.controllers":
        model_ep = EntryPoint(
            name="controller",
            value="mock_controller:MockController",
            group="redsun.plugins.controllers",
        )
        plugins.append(model_ep)
    return plugins

def mocked_ctrl_non_derived_info_entry_points(group: str) -> list[EntryPoint]:
    plugins = []
    if group == "redsun.plugins.controllers.config":
        info_ep = EntryPoint(
            name="controller",
            value="mock_controller:NonDerivedMotorInfo",
            group="redsun.plugins.controllers.config",
        )
        plugins.append(info_ep)

    if group == "redsun.plugins.controllers":
        model_ep = EntryPoint(
            name="controller",
            value="mock_controller:MockController",
            group="redsun.plugins.controllers",
        )
        plugins.append(model_ep)
    return plugins

def mocked_ctrl_non_derived_entry_points(group: str) -> list[EntryPoint]:
    plugins = []
    if group == "redsun.plugins.controllers.config":
        info_ep = EntryPoint(
            name="controller",
            value="mock_controller:MockControllerInfo",
            group="redsun.plugins.controllers.config",
        )
        plugins.append(info_ep)
    if group == "redsun.plugins.controllers":
        model_ep = EntryPoint(
            name="controller",
            value="mock_controller:NonDerivedController",
            group="redsun.plugins.controllers",
        )
        plugins.append(model_ep)
    return plugins
