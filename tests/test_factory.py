from pathlib import Path
from unittest import mock
from sunflare.virtual import VirtualBus
from redsun.controller.factory import BackendFactory

from conftest import side_effect

def test_model_factory(importlib_str: str, config_path: Path) -> None:

    with mock.patch(f"{importlib_str}.entry_points", side_effect=side_effect):
        from redsun.plugins import load_configuration

        config, types = load_configuration(str(config_path / 'mock_motor_config.yaml'))

        for info, class_type in zip(config.models, types["models"].values()):
            model = BackendFactory.build_model("motor", class_type, info)

            assert model is not None

def test_model_broken_factory(importlib_str: str, config_path: Path) -> None:
    with mock.patch(f"{importlib_str}.entry_points", side_effect=side_effect):
        from redsun.plugins import load_configuration

        config, types = load_configuration(str(config_path / 'broken_factory_model.yaml'))

        for info, class_type in zip(config.models, types["models"].values()):
            model = BackendFactory.build_model("motor", class_type, info)

            assert model is None

def test_controller_factory(importlib_str: str, config_path: Path) -> None:
    with mock.patch(f"{importlib_str}.entry_points", side_effect=side_effect):
        from redsun.plugins import load_configuration

        config, types = load_configuration(str(config_path / 'mock_controller_config.yaml'))

        for info, class_type in zip(config.models, types["controllers"].values()):
            ctrl = BackendFactory.build_controller("controller", class_type, info)

            assert ctrl is not None

def test_controller_broken_factory(importlib_str: str, config_path: Path) -> None:

    bus = VirtualBus()

    with mock.patch(f"{importlib_str}.entry_points", side_effect=side_effect):
        from redsun.plugins import load_configuration

        config, types = load_configuration(str(config_path / 'broken_factory_controller.yaml'))

        for info, class_type in zip(config.controllers, types["controllers"].values()):
            ctrl = BackendFactory.build_controller(name="controller", ctrl_info=info, ctrl_class=class_type, models={}, virtual_bus=bus)

            assert ctrl is None
