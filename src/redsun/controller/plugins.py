"""Redsun plugin manager module."""

from __future__ import annotations

import sys
from typing import (
    TYPE_CHECKING,
    Any,
    Optional,
    Tuple,
    Type,
    get_args,
    Literal,
    TypedDict,
)

from sunflare.controller import BaseController
from sunflare.engine import DetectorModel, MotorModel

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

from sunflare.config import (
    AcquisitionEngineTypes,
    FrontendTypes,
    DetectorModelInfo,
    MotorModelInfo,
    ControllerInfo,
    RedSunInstanceInfo,
)
from sunflare.log import get_logger

if TYPE_CHECKING:
    from redsun.view import BaseWidget


class InfoBackend(TypedDict):
    """Support typed dictionary for backend information models.

    Parameters
    ----------
    detectors : ``dict[str, DetectorModelInfo]``
        Dictionary of detector information models.
    motors : ``dict[str, MotorModelInfo]``
        Dictionary of motor information models.
    controllers : ``dict[str, ControllerInfo]``
        Dictionary of controller information models.
    """

    detectors: dict[str, DetectorModelInfo]
    motors: dict[str, MotorModelInfo]
    controllers: dict[str, ControllerInfo]


class Backend(TypedDict):
    """A support typed dictionary for backend models constructors.

    Parameters
    ----------
    detectors : ``dict[str, Type[DetectorModel[DetectorModelInfo]]]``
        Dictionary of detector device models.
    motors : ``dict[str, Type[MotorModel[MotorModelInfo]]]``
        Dictionary of motor device models.
    controllers : ``dict[str, Type[BaseController]``
        Dictionary of base controllers.
    """

    detectors: dict[str, Type[DetectorModel[DetectorModelInfo]]]
    motors: dict[str, Type[MotorModel[MotorModelInfo]]]
    controllers: dict[str, Type[BaseController]]


#: Plugin group names for the backend.
BACKEND_GROUPS = Literal["detectors", "motors", "controllers"]


class PluginManager:
    """Plugin manager class.

    This manager uses `importlib.metadata` to discover and load Redsun-compatible plugins.
    """

    @staticmethod
    def load_configuration(
        config_path: str,
    ) -> Tuple[RedSunInstanceInfo, Backend, dict[str, Type[BaseWidget]]]:
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
        config_groups = InfoBackend(detectors={}, motors={}, controllers={})
        types_groups = Backend(detectors={}, motors={}, controllers={})

        config = RedSunInstanceInfo.load_yaml(config_path)
        widgets_config: list[str] = config.pop("widgets")

        engine = AcquisitionEngineTypes(config.pop("engine"))
        frontend = FrontendTypes(config.pop("frontend"))

        # load the backend configuration
        types_groups, config_groups = PluginManager.load_backend(config)

        # load the frontend configuration
        frontend_types: dict[str, Type[BaseWidget]]
        if widgets_config:
            frontend_types = PluginManager.load_frontend(widgets_config)
        else:
            frontend_types = {}

        # build configuration
        output_config = RedSunInstanceInfo(
            engine=engine, frontend=frontend, **config_groups
        )

        return output_config, types_groups, frontend_types

    @staticmethod
    def load_frontend(config: list[str]) -> dict[str, Type[BaseWidget]]:
        """Load the frontend configuration.

        Parameters
        ----------
        config : ``list[str]``
            List of widget class names.

        Returns
        -------
        ``dict[str, Type[BaseWidget]]``
            Frontend configuration.
        """
        # Get the entry points for the current group.
        # Plugins not found will be tagged with None
        plugins = entry_points(group="redsun.plugins.widgets")
        widgets: dict[str, Optional[Type[BaseWidget]]] = {
            widget_name: next(
                (ep.load() for ep in plugins if ep.name == widget_name), None
            )
            for widget_name in config
        }

        # Remove all entries with None values
        filtered_widgets: dict[str, Type[BaseWidget]] = {
            key: value for key, value in widgets.items() if value is not None
        }

        return filtered_widgets

    @staticmethod
    def load_backend(config: dict[str, Any]) -> Tuple[Backend, InfoBackend]:
        """Load the backend configuration.

        Parameters
        ----------
        config : ``dict[str, Any]``
            Configuration dictionary.

        Returns
        -------
        Backend
            Backend configuration.
        """
        logger = get_logger()

        groups: list[BACKEND_GROUPS] = list(get_args(BACKEND_GROUPS))
        config_groups = InfoBackend(detectors={}, motors={}, controllers={})
        types_groups = Backend(detectors={}, motors={}, controllers={})

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
                        [
                            issubclass(info_builder, info_type)
                            for info_type in [DetectorModelInfo, MotorModelInfo]
                        ]
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
        return types_groups, config_groups
