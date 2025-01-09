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
    FrontendTypes,
    ModelInfo,
    RedSunSessionInfo,
)
from sunflare.log import get_logger

if TYPE_CHECKING:
    if sys.version_info < (3, 10):
        from importlib_metadata import EntryPoint
    else:
        from importlib.metadata import EntryPoint

    from sunflare.controller import ControllerProtocol
    from sunflare.model import ModelProtocol
    from sunflare.view import WidgetProtocol


class InfoBackend(TypedDict):
    """A support typed dictionary for backend information models.

    Parameters
    ----------
    detectors : ``dict[str, DetectorModelInfo]``
        Dictionary of detector information models.
    models : ``dict[str, ModelInfo]``
        Dictionary of model informations.
    controllers : ``dict[str, ControllerInfo]``
        Dictionary of controller informations.
    """

    models: dict[str, ModelInfo]
    controllers: dict[str, ControllerInfo]


class Backend(TypedDict):
    """A support typed dictionary for backend models constructors.

    Parameters
    ----------
    models : ``dict[str, type[ModelProtocol]``
        Dictionary of base models.
    controllers : ``dict[str, type[ControllerProtocol]``
        Dictionary of base controllers.
    """

    models: dict[str, type[ModelProtocol]]
    controllers: dict[str, type[ControllerProtocol]]


class Plugin(NamedTuple):
    """A named tuple representing the elements required to identify and load a plugin.

    Parameters
    ----------
    name : ``str``
        The name of the plugin.
    info : ``type[object]``
        The information class for the plugin.
    base_class : ``type[object]``
        The base class for the plugin.
    """

    name: str
    info: type[object]
    base_class: type[object]


#: Plugin group names for the backend.
PLUGIN_GROUPS = Literal["models", "controllers"]


class PluginManager:
    """Plugin manager class.

    This manager uses `importlib.metadata` to discover and load Redsun-compatible plugins.
    """

    @staticmethod
    def load_configuration(
        config_path: str,
    ) -> Tuple[RedSunSessionInfo, Backend, dict[str, type[WidgetProtocol]]]:
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
        Tuple[RedSunSessionInfo, dict[str, Types], dict[str, type[BaseController]]
            RedSun instance configuration and class types to build.
        """
        widgets_config: list[str]

        config = RedSunSessionInfo.load_yaml(config_path)
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
        frontend_types: dict[str, type[WidgetProtocol]]
        if widgets_config:
            frontend_types = PluginManager.load_frontend(widgets_config)
        else:
            frontend_types = {}

        # build configuration
        output_config = RedSunSessionInfo(
            engine=engine, frontend=frontend, **config_groups
        )

        return output_config, types_groups, frontend_types

    @staticmethod
    def load_frontend(config: list[str]) -> dict[str, type[WidgetProtocol]]:
        """Load the frontend configuration.

        Parameters
        ----------
        config : ``list[str]``
            List of widget class names.

        Returns
        -------
        ``dict[str, type[WidgetProtocol]]``
            Frontend configuration.
        """
        # Get the entry points for the current group.
        # Plugins not found will be tagged with None
        plugins = entry_points(group="redsun.plugins.widgets")
        widgets: dict[str, Optional[type[WidgetProtocol]]] = {
            widget_name: next(
                (ep.load() for ep in plugins if ep.name == widget_name), None
            )
            for widget_name in config
        }

        # Remove all entries with None values
        filtered_widgets: dict[str, type[WidgetProtocol]] = {
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
        groups: list[PLUGIN_GROUPS] = list(get_args(PLUGIN_GROUPS))
        config_groups = InfoBackend(models={}, controllers={})
        types_groups = Backend(models={}, controllers={})

        for group in groups:
            # if the group is not in
            # the configuration, skip it
            if group not in config:
                continue

            # the key for the class name is either "model_name" for models
            # or "controller_name" for controllers; it's made so
            # we can more easily recognize the type of plugin
            class_name_key = (
                "model_name" if group != "controllers" else "controller_name"
            )

            loaded_plugins = PluginManager.load_backend_plugins(group)

            for plugin_id, plugin_config in config[group].items():
                if plugin_config[class_name_key] not in loaded_plugins:
                    continue
                builder = loaded_plugins[plugin_config[class_name_key]].info
                model = loaded_plugins[plugin_config[class_name_key]].base_class

                # type checker complains about the assignment because
                # it doesn't discern between type[object] and type[ModelInfo] or type[ControllerInfo];
                # the assignment is correct, so we ignore the warning
                config_groups[group][plugin_id] = builder(**plugin_config)  # type: ignore[assignment]
                types_groups[group][plugin_id] = model  # type: ignore[assignment]

        return types_groups, config_groups

    @staticmethod
    def load_backend_plugins(group: PLUGIN_GROUPS) -> dict[str, Plugin]:
        """Load the plugins.

        Parameters
        ----------
        config : ``dict[str, Any]``
            The configuration dictionary.

        Returns
        -------
        ``dict[str, Plugin]``
            The plugin configuration and base classes.
        """
        logger = get_logger()

        output_plugins: dict[str, Plugin] = {}

        # get the entry points for the current group
        plugin_group = f"redsun.plugins.{group}"
        info_plugins: list[EntryPoint] = list(
            entry_points(group=f"{plugin_group}.config")
        )
        plugins: list[EntryPoint] = list(entry_points(group=plugin_group))

        # the two lists must have the same length
        if len(info_plugins) != len(plugins):
            # find the model plugins that do not have a
            # corresponding info plugin and remove them
            missing_plugins = [
                ep for ep in plugins if ep.name not in [ep.name for ep in info_plugins]
            ]
            for missing_plugin in missing_plugins:
                plugins.remove(missing_plugin)
            missing_plugins_values = [ep.value for ep in missing_plugins]
            logger.warning(
                f"The following classes do not have a corresponding information model: {missing_plugins_values}. They will not be loaded."
            )

        for info_ep in info_plugins:
            # find the corresponding model plugin; they match by the value of "ep.name"
            plugin_ep = next((ep for ep in plugins if ep.name == info_ep.name), None)

            # if the model plugin is not found, skip the info plugin
            if plugin_ep is None:
                continue
            info_builder = info_ep.load()
            if not any(
                [
                    issubclass(info_builder, info_type)
                    for info_type in [ModelInfo, ControllerInfo]
                ]
            ):
                logger.warning(
                    f"Loaded model info {info_ep.value} is not a subclass "
                    f"of any recognized model info class. "
                    f"Plugin will not be loaded."
                )
                continue
            base_class = plugin_ep.load()
            # the model key is the last part of the value
            model_key = plugin_ep.value.split(":")[-1]
            output_plugins[model_key] = Plugin(
                name=model_key, info=info_builder, base_class=base_class
            )

        return output_plugins
