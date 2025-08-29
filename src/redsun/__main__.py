"""Redsun main entry point."""

from __future__ import annotations

import argparse
import logging
import sys

from sunflare.virtual import VirtualBus

from redsun import plugins
from redsun.controller import RedsunController
from redsun.view import build_view_layer, create_app, launch_app


class RedSunArgs(argparse.Namespace):
    """type hints for command line arguments."""

    config: str
    debug: bool


def parse_args() -> RedSunArgs:
    """Parse command line arguments.

    Returns
    -------
    RedSunArgs
        Parsed command line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Redsun: event-driven data acquisition system"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="Absolute path to the YAML configuration file",
        required=True,
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug logging",
        default=False,
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
    # create the application
    app = create_app()

    # virtual layer
    virtual_bus = VirtualBus()

    # get the startup configuration
    config, types_groups = plugins.load_configuration(input_config)

    # build the controller layer
    controller = RedsunController(config, virtual_bus, types_groups)

    # build the view layer
    view = build_view_layer(config, types_groups["views"], virtual_bus)

    # connect the controller and the view to the virtual layer
    controller.connect_to_virtual()
    view.connect_to_virtual()

    # launch the application;
    # the app starts here and
    # there is no return until it's closed
    launch_app(app, view)


def main_cli() -> None:
    """Command line entry point for the Redsun application."""
    args = parse_args()
    logger = logging.getLogger("redsun")
    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    main(args.config)


if __name__ == "__main__":
    main_cli()
