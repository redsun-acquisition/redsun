"""RedSun main entry point."""

from __future__ import annotations

import argparse
import sys

from sunflare.virtualbus import ModuleVirtualBus

from redsun.controller import PluginManager, RedSunMainHardwareController
from redsun.view import build_view_layer, launch_app
from redsun.virtual import HardwareVirtualBus


class RedSunArgs(argparse.Namespace):
    """Type hints for command line arguments."""

    config: str


def parse_args() -> RedSunArgs:
    """Parse command line arguments.

    Returns
    -------
    RedSunArgs
        Parsed command line arguments.
    """
    parser = argparse.ArgumentParser(
        description="RedSun: event-driven data acquisition system"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="Absolute path to the YAML configuration file",
        required=True,
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args: RedSunArgs = parser.parse_args(namespace=RedSunArgs())
    return args


def main(input_config: str) -> None:
    """Redsun application entry point.

    Parameters
    ----------
    input_config : str
        Path to the configuration file.
    """
    # virtual layer
    module_bus = ModuleVirtualBus()
    hardware_bus = HardwareVirtualBus()

    # get the startup configuration
    config, types_groups = PluginManager.load_configuration(input_config)

    models = {group: types_groups.get(group, {}) for group in ["detectors", "motors"]}
    controllers = types_groups.get("controllers", {})
    widgets = types_groups.get("widgets", {})

    # build the controller layer
    controller = RedSunMainHardwareController(
        config, models, controllers, hardware_bus, module_bus
    )

    # build the view layer;
    # the app starts here and
    # there is no return until it's closed
    app, view = build_view_layer(config, widgets)
    controller.connect_to_virtual()
    view.connect_to_virtual()
    launch_app(app, view)


def main_cli() -> None:
    """Command line entry point for the RedSun application."""
    args = parse_args()
    main(args.config)


if __name__ == "__main__":
    main_cli()
