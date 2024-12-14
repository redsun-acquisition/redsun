"""RedSun main entry point."""

from __future__ import annotations

import argparse

from sunflare.virtualbus import ModuleVirtualBus
from redsun.controller import PluginManager, HardwareVirtualBus, build_controller_layer
from redsun.view import build_view_layer


class RedSunArgs(argparse.Namespace):
    """Type hints for command line arguments."""

    config_file: str


def parse_args() -> RedSunArgs:
    """Parse command line arguments.

    Returns
    -------
    RedSunArgs
        Parsed command line arguments.
    """
    parser = argparse.ArgumentParser(description="RedSun application")
    parser.add_argument(
        "-c", "--config", type=str, help="Absolute path to the YAML configuration file"
    )
    args: RedSunArgs = parser.parse_args(namespace=RedSunArgs())
    return args


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
    plugin_manager = PluginManager()

    # get the startup configuration
    registry = plugin_manager.load_startup_configuration(config)

    # build the controller layer
    main_controller = build_controller_layer(config, registry, hardware_bus, module_bus)

    # build the view layer;
    # the app starts here and
    # there is no return until the app is closed
    build_view_layer(main_controller)


if __name__ == "__main__":
    args = parse_args()
    main(args.config_file)
