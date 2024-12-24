"""Redsun plugin manager module."""

from __future__ import annotations

import sys
from typing import Any, Tuple, Type, Union

from sunflare.config import (
    ControllerInfo,
    DetectorModelInfo,
    MotorModelInfo,
    RedSunInstanceInfo,
)
from sunflare.controller import BaseController
from sunflare.engine import DetectorModel, MotorModel
from sunflare.log import get_logger

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

InfoTypes = Union[Type[DetectorModelInfo], Type[MotorModelInfo], Type[ControllerInfo]]
Types = Union[
    Type[DetectorModel[DetectorModelInfo]],
    Type[MotorModel[MotorModelInfo]],
    Type[BaseController],
]


class PluginManager:
    """Plugin manager class.

    This manager uses `importlib.metadata` to discover and load Redsun-compatible plugins.
    """

    @staticmethod
    def load_configuration(
        config_path: str,
    ) -> Tuple[RedSunInstanceInfo, dict[str, Types]]:
        """Load the configuration from a YAML file.

        The manager will load the configuration from the input YAML file.
        It will then load the information models and device models for each group.
        The information models are built here; the actual device models are built in the factory.

        Parameters
        ----------
        config_path : ``str``
            Path to the YAML file.

        Returns
        -------
        Tuple[RedSunInstanceInfo, dict[str, Types], dict[str, Type[BaseController]]
            RedSun instance configuration and class types to build.
        """
        logger = get_logger()
        config = RedSunInstanceInfo.load_yaml(config_path)
        groups = [
            group for group in config.keys() if group not in ["engine", "frontend"]
        ]

        config_groups: dict[str, dict[str, InfoTypes]] = {group: {} for group in groups}
        types_groups: dict[str, dict[str, Types]] = {group: {} for group in groups}

        for group in groups:
            # get the configuration for the current group;
            # the key is the device name; the value is the device configuration
            input: dict[str, Any] = config[group]

            # get the entry points for the current group
            plugins = entry_points(group=".".join(["redsun.plugins", group]))
            info_plugins = [ep for ep in plugins if "_config" in ep.name]
            model_plugins = [ep for ep in plugins if "_config" not in ep.name]

            # the two lists must have the same length
            if len(info_plugins) != len(model_plugins):
                # find the model plugins that do not have a
                # corresponding info plugin and remove them
                missing_plugins = [
                    ep
                    for ep in model_plugins
                    if ep.name not in [ep.name for ep in info_plugins]
                ]
                for missing_plugin in missing_plugins:
                    model_plugins.remove(missing_plugin)
                logger.error(
                    f"The following models do not have a corresponding information model: {missing_plugins}. They will not be loaded."
                )

            # the information models are built here;
            # the actual device models are built in the factory
            for info_ep, model_ep in zip(info_plugins, model_plugins):
                # Retrieve the name of the information model
                info_cls = info_ep.value.split(":")[1]
                # Retrieve the name of the actual device model
                build_cls = info_cls[:-4]
                try:
                    info_builder = info_ep.load()
                    if not all(
                        [issubclass(info_builder, info_type) for info_type in InfoTypes]
                    ):
                        raise TypeError(
                            f"Loaded model info {info_cls} is not a subclass "
                            f"of any recognized model info class. "
                            f"Plugin will not be loaded."
                        )
                except TypeError as e:
                    # the information model is not a subclass of any recognized model info class
                    # log the error and skip the plugin
                    logger.error(e)
                    continue
                except Exception as e:
                    # something went wrong while loading the plugin;
                    # log the error and skip the plugin
                    logger.error(
                        f"Failed to load information model {info_ep.name}: {e}. Plugin will not be loaded."
                    )
                    continue

                # inspect the current device configuration
                for device_name, values in input.items():
                    if values["model_name"] == build_cls:
                        # build the information model
                        information = info_builder(**values)

                        # load the device model
                        constructor = model_ep.load()

                        config_groups[group][device_name] = information
                        types_groups[group][device_name] = constructor
                        break
                # pop the found device from the input to speed up the search
                input.pop(device_name)

        # build configuration
        config = RedSunInstanceInfo(**config_groups)

        return config, types_groups
