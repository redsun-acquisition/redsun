"""RedSun main entry point."""

from __future__ import annotations

from sunflare.virtualbus import ModuleVirtualBus
from redsun.controller import PluginManager, HardwareVirtualBus, build_controller_layer


def main(input_config: str) -> None:
    """Redsun application entry point.

    Parameters
    ----------
    input_config : str
        Path to the configuration file.
    """
    # load configuration
    config = PluginManager.load_and_check_yaml(input_config)

    # TODO: handle the case where config is None
    if config is None:
        return

    # virtual layer
    module_bus = ModuleVirtualBus()
    hardware_bus = HardwareVirtualBus()
    plugin_manager = PluginManager(hardware_bus, module_bus)

    # get the startup configuration
    registry = plugin_manager.load_startup_configuration(config)

    # build the controller layer
    main_controller = build_controller_layer(config, registry)


if __name__ == "__main__":
    main(str())
