import json
import os

from redsun.engine.exengine import ExEngineHandler
from redsun.controller import RedSunHardwareController
from redsun.controller.virtualbus import HardwareVirtualBus

from sunflare.virtualbus import ModuleVirtualBus
from sunflare.config import RedSunInstanceInfo

config_path = os.path.join(os.path.dirname(__file__), "data")


def test_controller_creation() -> None:
    """Test the creation of the main hardware controller."""

    config_file = os.path.join(config_path, "empty_config.json")
    config_dict = json.load(open(config_file))
    config = RedSunInstanceInfo(**config_dict)

    virtual_bus = HardwareVirtualBus()
    module_bus = ModuleVirtualBus()
    controller = RedSunHardwareController(config, virtual_bus, module_bus)

    assert isinstance(controller.virtual_bus, HardwareVirtualBus)
    assert isinstance(controller.module_bus, ModuleVirtualBus)
    assert isinstance(controller.handler, ExEngineHandler)

    # engine needs to be shutdown
    # for test to correctly finish
    controller.handler.shutdown()
