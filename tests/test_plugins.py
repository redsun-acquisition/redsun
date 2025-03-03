from pathlib import Path
from unittest import mock
from sunflare.config import RedSunSessionInfo

import sys
if sys.version_info <= (3, 9):
    from importlib_metadata import EntryPoint
else:
    from importlib.metadata import EntryPoint

from conftest import side_effect

def test_fake_entrypoint(importlib_str: str) -> None:
    with mock.patch(f"{importlib_str}.entry_points", side_effect=side_effect) as entry_points:
        ep = entry_points(group='redsun.plugins')
        assert len(ep) == 1
        assert ep[0].name == 'mock-pkg'
        assert ep[0].value == 'redsun.yaml'
        assert ep[0].group == 'redsun.plugins'


def test_plugin_loading(importlib_str: str, config_path: Path) -> None:

    with mock.patch(f"{importlib_str}.entry_points", side_effect=side_effect) as entry_points:
        from redsun.plugins import _load_plugins
        config = RedSunSessionInfo.load_yaml(str(config_path / 'mock_motor_config.yaml'))
        manifests = entry_points(group='redsun.plugins')
        plugins = _load_plugins(group_cfg=config["models"], group='models', available_manifests=manifests)

    assert len(plugins) != 0

    from mock_pkg.model import MyMotorInfo, MyMotor, NonDerivedMotor, NonDerivedMotorInfo

    target = [(MyMotor, MyMotorInfo), (NonDerivedMotor, NonDerivedMotorInfo)]

    for plugin, t in zip(plugins, target):
        assert plugin.base_class == t[0]
        assert isinstance(plugin.info, t[1])

def test_motor_configuration(importlib_str: str, config_path: Path) -> None:

    with mock.patch(f"{importlib_str}.entry_points", side_effect=side_effect):
        from redsun.plugins import load_configuration

        config, types = load_configuration(str(config_path / 'mock_motor_config.yaml'))

    assert len(config.models) == 2
    assert len(config.controllers) == 0
    assert len(config.widgets) == 0

    from mock_pkg.model import MyMotorInfo, MyMotor, NonDerivedMotor, NonDerivedMotorInfo

    for i, model in enumerate(config.models.values()):
        if i == 0:
            assert isinstance(model, MyMotorInfo)
        else:
            assert isinstance(model, NonDerivedMotorInfo)

    assert len(types["models"]) == 2
    assert len(types["controllers"]) == 0
    assert len(types["widgets"]) == 0

    for i, class_type in enumerate(types["models"].values()):
        if i == 0:
            assert class_type == MyMotor
        else:
            assert class_type == NonDerivedMotor

def test_detector_configuration(importlib_str: str, config_path: Path) -> None:
    with mock.patch(f"{importlib_str}.entry_points", side_effect=side_effect):
        from redsun.plugins import load_configuration

        config, types = load_configuration(str(config_path / 'mock_detector_config.yaml'))

    assert len(config.models) == 2
    assert len(config.controllers) == 0
    assert len(config.widgets) == 0

    from mock_pkg.model import MockDetector, MockDetectorInfo

    for model in config.models.values():
        assert isinstance(model, MockDetectorInfo)

    assert len(types["models"]) == 2
    assert len(types["controllers"]) == 0
    assert len(types["widgets"]) == 0

    for class_type in types["models"].values():
        assert class_type == MockDetector

def test_controller_configuration(importlib_str: str, config_path: Path) -> None:
    with mock.patch(f"{importlib_str}.entry_points", side_effect=side_effect):
        from redsun.plugins import load_configuration

        config, types = load_configuration(str(config_path / 'mock_controller_config.yaml'))

    assert len(config.models) == 0
    assert len(config.controllers) == 1
    assert len(config.widgets) == 0

    from mock_pkg.controller import MockController, MockControllerInfo

    for ctrl in config.controllers.values():
        assert isinstance(ctrl, MockControllerInfo)

    assert len(types["models"]) == 0
    assert len(types["controllers"]) == 1
    assert len(types["widgets"]) == 0

    for class_type in types["controllers"].values():
        assert class_type == MockController

def test_broken_model_configuration(importlib_str: str, config_path: Path) -> None:
    with mock.patch(f"{importlib_str}.entry_points", side_effect=side_effect):
        from redsun.plugins import load_configuration
        config, types = load_configuration(str(config_path / 'broken_model_config.yaml'))

        assert len(config.models) == 1
        assert len(config.controllers) == 0
        assert len(config.widgets) == 0

        from mock_pkg.model import MockDetector, MockDetectorInfo

        assert isinstance(list(config.models.values())[0], MockDetectorInfo)
        for class_type in types["models"].values():
            assert class_type == MockDetector

def test_hidden_model_configuration(importlib_str: str, config_path: Path) -> None:
    with mock.patch(f"{importlib_str}.entry_points", side_effect=side_effect):
        from redsun.plugins import load_configuration
        config, types = load_configuration(str(config_path / 'hidden_model_config.yaml'))

        assert len(config.models) == 1
        assert len(config.controllers) == 0
        assert len(config.widgets) == 0

        from mock_pkg.model.hidden import HiddenModel, HiddenModelInfo

        assert isinstance(list(config.models.values())[0], HiddenModelInfo)
        for class_type in types["models"].values():
            assert class_type == HiddenModel
