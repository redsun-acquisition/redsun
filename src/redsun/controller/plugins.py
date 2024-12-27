"""Redsun plugin manager module."""

from __future__ import annotations

import sys
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    NamedTuple,
    Optional,
    Tuple,
    Type,
    TypedDict,
    get_args,
)

if sys.version_info < (3, 10):  # pragma: no cover
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

from sunflare.config import (
    AcquisitionEngineTypes,
    ControllerInfo,
    DetectorModelInfo,
    FrontendTypes,
    MotorModelInfo,
    RedSunInstanceInfo,
)
from sunflare.log import get_logger

if TYPE_CHECKING:
    if sys.version_info < (3, 10):
        from importlib_metadata import EntryPoint
    else:
        from importlib.metadata import EntryPoint

    from sunflare.controller import BaseController
    from sunflare.engine import DetectorModel, MotorModel

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


class Plugin(NamedTuple):
    """A named tuple representing the elements required to identify and load a plugin.

    Parameters
    ----------
    name : ``str``
        The name of the plugin.
    info : ``Type[object]``
        The information class for the plugin.
    base_class : ``Type[object]``
        The base class for the plugin.
    """

    name: str
    info: Type[object]
    base_class: Type[object]


#: Plugin group names for the backend.
MODEL_GROUPS = Literal["detectors", "motors"]


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
        widgets_config: list[str]
        config_groups = InfoBackend(detectors={}, motors={}, controllers={})
        types_groups = Backend(detectors={}, motors={}, controllers={})

        config = RedSunInstanceInfo.load_yaml(config_path)
        try:
            widgets_config = config.pop("widgets")
        except KeyError:
            # no widgets configuration found
            widgets_config = []

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
        groups: list[MODEL_GROUPS] = list(get_args(MODEL_GROUPS))
        config_groups = InfoBackend(detectors={}, motors={}, controllers={})
        types_groups = Backend(detectors={}, motors={}, controllers={})

        for group in groups:
            # if the group is not in
            # the configuration, skip it
            if group not in config:
                continue

            loaded_plugins = PluginManager.load_model_plugins(group)

            for device_name, model_config in config[group].items():
                if model_config["model_name"] not in loaded_plugins:
                    continue
                builder = loaded_plugins[model_config["model_name"]].info
                model = loaded_plugins[model_config["model_name"]].base_class

                # these types are correct so we can safely ignore the type checker
                config_groups[group][device_name] = builder(**model_config)  # type: ignore
                types_groups[group][device_name] = model  # type: ignore

        return types_groups, config_groups

    @staticmethod
    def load_model_plugins(group: MODEL_GROUPS) -> dict[str, Plugin]:
        """Load the plugins.

        Parameters
        ----------
        config : ``dict[str, Any]``
            The configuration dictionary.

        Returns
        -------
        ``Tuple[dict[str, Any], dict[str, Any]]``
            The configuration and model classes.
        """
        logger = get_logger()

        output_plugins: dict[str, Plugin] = {}

        # get the entry points for the current group
        plugin_group = f"redsun.plugins.{group}"
        info_plugins: list[EntryPoint] = list(
            entry_points(group=f"{plugin_group}.config")
        )
        model_plugins: list[EntryPoint] = list(entry_points(group=plugin_group))

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
            missing_plugins_values = [ep.value for ep in missing_plugins]
            logger.error(
                f"The following models do not have a corresponding information model: {missing_plugins_values}. They will not be loaded."
            )

        for info_ep in info_plugins:
            # find the corresponding model plugin; they match by the value of "ep.name"
            model_ep = next(
                (ep for ep in model_plugins if ep.name == info_ep.name), None
            )

            # if the model plugin is not found, skip the info plugin
            if model_ep is None:
                continue
            try:
                info_builder = info_ep.load()
                if not any(
                    [
                        issubclass(info_builder, info_type)
                        for info_type in [DetectorModelInfo, MotorModelInfo]
                    ]
                ):
                    raise TypeError(
                        f"Loaded model info {info_ep.value} is not a subclass "
                        f"of any recognized model info class. "
                        f"Plugin will not be loaded."
                    )
            except TypeError as e:
                # the information model is not a subclass of any recognized model info class
                # log the error and skip the plugin
                logger.error(e)
                continue
            base_class = model_ep.load()
            # the model key is the last part of the value
            model_key = model_ep.value.split(":")[-1]
            output_plugins[model_key] = Plugin(
                name=model_key, info=info_builder, base_class=base_class
            )

        return output_plugins
