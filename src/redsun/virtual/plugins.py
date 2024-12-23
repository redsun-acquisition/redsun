"""Redsun plugin manager module."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import yaml
from sunflare.log import get_logger

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

if TYPE_CHECKING:
    from typing import Any, Optional

    from sunflare.config import DetectorModelInfo, MotorModelInfo

    from redsun.common import RedSunConfigInfo, Registry


class PluginManager:
    """Plugin manager class.

    This manager uses `importlib.metadata` to discover and load Redsun-compatible plugins.
    """

    @staticmethod
    def load_and_check_yaml(config_path: str) -> Optional[RedSunConfigInfo]:
        """Check the configuration file.

        If an error occurs, the function logs the error and returns an empty dictionary.

        Parameters
        ----------
        config_path : str
            Path to the configuration file.

        Returns
        -------
        Tuple[dict[str, Any], list[str]]
            A tuple containing:
            - The configuration dictionary.
            - A list of plugin groups to check.
        """
        logger = get_logger()

        config: Optional[RedSunConfigInfo]
        try:
            with open(config_path, "r") as file:
                config = yaml.safe_load(file)
            # check that config has "engine" and "frontend" keys
            if config is not None and not all(
                [key in config.keys() for key in ["engine", "frontend"]]
            ):
                logger.error(
                    "Configuration file does not specify an engine or a frontend."
                )
                config = None
        except yaml.YAMLError as e:
            logger.exception(f"Error parsing configuration file: {e}")
            config = None
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_path}")
            config = None
        return config

    @staticmethod
    def load_startup_configuration(config: RedSunConfigInfo) -> Registry:
        """Load the startup configuration.

        Parameters
        ----------
        config : RedSunConfigInfo
            Configuration dictionary.

        Returns
        -------
        Registry
            A dictionary containing the loaded plugins classes.
            - keys: group names (i.e. "motors", "detectors")
            - values: list of tuples containing:
                - device name
                - model info class
                - model class
        """
        groups = [
            group for group in config.keys() if group not in ["engine", "frontend"]
        ]

        # TODO: load_plugins expects a dictionary, but the config is a TypedDict;
        #       this should be fixed in the future, or accept it as it is
        return PluginManager.load_plugins(config, groups)  # type: ignore

    @staticmethod
    def load_plugins(config: dict[str, Any], groups: list[str]) -> Registry:
        """Load plugins from the given configuration.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration dictionary.
        groups : list[str]
            List of groups to load plugins from.

        Returns
        -------
        Registry
            A dictionary containing the loaded plugins classes.
            - keys: group names (i.e. "motors", "detectors")
            - values: list of tuples containing:
                - device name
                - model info class
                - model class
        """
        registry: Registry = {group: [] for group in groups}
        for group in groups:
            input: dict[str, Any] = config[group]
            plugins = entry_points(group=".".join(["redsun.plugins", group]))
            config_plugins = [ep for ep in plugins if "_config" in ep.name]
            model_plugins = [ep for ep in plugins if "_config" not in ep.name]
            for cfg_ep, model_ep in zip(config_plugins, model_plugins):
                # Retrieve the name of the config builder
                cfg_cls = cfg_ep.value.split(":")[1]
                # Retrieve the name of the actual device model
                bld_cls = cfg_cls[:-4]
                cfg_builder = cfg_ep.load()
                if not all(
                    [
                        issubclass(cfg_builder, cfg_type)
                        for cfg_type in [DetectorModelInfo, MotorModelInfo]
                    ]
                ):
                    raise TypeError(
                        f"Loaded model info {cfg_builder} is not a subclass of any recognized model info class"
                    )
                for device_name, values in input.items():
                    if values["model_name"] == bld_cls:
                        builder = model_ep.load()
                        registry[group].append((device_name, cfg_builder, builder))
                        break
                # pop the found device from the input to speed up the search
                input.pop(device_name)
        return registry
