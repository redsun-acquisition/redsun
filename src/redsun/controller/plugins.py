"""Redsun plugin manager module."""

from __future__ import annotations

import logging
import sys
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    NamedTuple,
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
    WidgetInfo,
)

if TYPE_CHECKING:
    if sys.version_info < (3, 10):
        from importlib_metadata import EntryPoint
    else:
        from importlib.metadata import EntryPoint

    from sunflare.controller import ControllerProtocol
    from sunflare.model import ModelProtocol
    from sunflare.view import WidgetProtocol

logger = logging.getLogger("redsun")


class PluginInfoDict(TypedDict):
    """A support typed dictionary for backend information models.

    Parameters
    ----------
    models : ``dict[str, ModelInfo]``
        Dictionary of model informations.
    controllers : ``dict[str, ControllerInfo]``
        Dictionary of controller informations.
    widgets : ``dict[str, WidgetInfo]``
        Dictionary of widget informations.
    """

    models: dict[str, ModelInfo]
    controllers: dict[str, ControllerInfo]
    widgets: dict[str, WidgetInfo]


class PluginDict(TypedDict):
    """A support typed dictionary for backend models constructors.

    Parameters
    ----------
    models : ``dict[str, type[ModelProtocol]``
        Dictionary of models classes.
    controllers : ``dict[str, type[ControllerProtocol]``
        Dictionary of controllers classes.
    widgets : ``dict[str, type[WidgetProtocol]``
        Dictionary of widgets classes.
    """

    models: dict[str, type[ModelProtocol]]
    controllers: dict[str, type[ControllerProtocol]]
    widgets: dict[str, type[WidgetProtocol]]


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
PLUGIN_GROUPS = Literal["models", "controllers", "widgets"]


class PluginManager:
    """Plugin manager class.

    This manager uses `importlib.metadata` to discover and load Redsun-compatible plugins.
    """

    @staticmethod
    def load_configuration(
        config_path: str,
    ) -> tuple[RedSunSessionInfo, PluginDict]:
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
        tuple[RedSunSessionInfo, dict[str, Types], dict[str, type[BaseController]]
            Redsun instance configuration and class types to build.
        """
        config = RedSunSessionInfo.load_yaml(config_path)

        session = config.pop("session", "Redsun")
        try:
            engine = AcquisitionEngineTypes(config.pop("engine"))
            frontend = FrontendTypes(config.pop("frontend"))
        except KeyError as e:
            raise KeyError(f"Configuration file {config_path} is missing the key {e}.")

        # load the session configuration
        types_groups, config_groups = PluginManager.__load_session(config)

        # build configuration
        output_config = RedSunSessionInfo(
            session=session, engine=engine, frontend=frontend, **config_groups
        )

        return output_config, types_groups

    @staticmethod
    def __load_session(config: dict[str, Any]) -> tuple[PluginDict, PluginInfoDict]:
        """Load the plugins for the current session.

        The method will load the plugins bundled into three groups:

        - models ("redsun.plugins.models" and "redsun.plugins.models.config");
        - controllers ("redsun.plugins.controllers" and "redsun.plugins.controllers.config");
        - widgets ("redsun.plugins.widgets" and "redsun.plugins.widgets.config").

        Parameters
        ----------
        config : ``dict[str, Any]``
            Configuration dictionary.

        Returns
        -------
        ``tuple[PluginDict, PluginInfoDict]``
            Full configuration for the current session.
        """
        groups: set[PLUGIN_GROUPS] = set(get_args(PLUGIN_GROUPS))
        config_groups = PluginInfoDict(models={}, controllers={}, widgets={})
        types_groups = PluginDict(models={}, controllers={}, widgets={})

        for group in groups:
            # if the group is not in
            # the configuration, skip it
            if group not in config:
                continue

            loaded_plugins = PluginManager.__load_plugins(group)

            # if the plugin is a model, we use the "model_name" key
            # to correctily recognize the builder; otherwise,
            # if the plugin is a controller, it will be recognized
            # from the key "plugin_id" in the configuration
            class_name_key = "model_name" if group == "models" else ""

            for plugin_id, plugin_config in config[group].items():
                if group != "models":
                    class_name_key = plugin_id
                    info = loaded_plugins[plugin_id].info
                    base_class = loaded_plugins[plugin_id].base_class
                else:  # group == "models"
                    if plugin_config[class_name_key] not in loaded_plugins:
                        continue
                    info = loaded_plugins[plugin_config[class_name_key]].info
                    base_class = loaded_plugins[
                        plugin_config[class_name_key]
                    ].base_class

                # mypy complains about the assignment because it doesn't discern
                # between type[object] and the specific plugin info type;
                # still, the assignment is correct, so we ignore the warning
                config_groups[group][plugin_id] = info(**plugin_config)  # type: ignore[assignment]
                types_groups[group][plugin_id] = base_class  # type: ignore[assignment]

        return types_groups, config_groups

    @staticmethod
    def __load_plugins(group: PLUGIN_GROUPS) -> dict[str, Plugin]:
        """Load the plugins.

        The method will inspect the entry points corresponding to
        ``redsun.plugins.{group}`` and ``redsun.plugins.{group}.config``.

        Plugins are expected to have a corresponding information class
        that is a subclass of ``ModelInfo``, ``ControllerInfo``, or ``WidgetInfo``.

        Whenever a plugin is found that does not have a corresponding information class,
        a warning will be issued, and the plugin will not be loaded.

        Parameters
        ----------
        group : ``Literal["models", "controllers", "widgets"]``
            The group of plugins to load.

        Returns
        -------
        ``dict[str, Plugin]``
            The plugin configuration and base classes.
        """
        logger = logging.getLogger("redsun")

        output_plugins: dict[str, Plugin] = {}

        # get the entry points for the current group
        plugin_group = f"redsun.plugins.{group}"
        info_plugins: list[EntryPoint] = list(
            entry_points(group=f"{plugin_group}.config")
        )
        plugins: list[EntryPoint] = list(entry_points(group=plugin_group))

        # the two lists must have the same length
        if len(info_plugins) != len(plugins):
            # find the plugins that do not have a
            # corresponding info plugin and remove them
            missing_plugins = [
                ep for ep in plugins if ep.name not in [ep.name for ep in info_plugins]
            ]
            for missing_plugin in missing_plugins:
                plugins.remove(missing_plugin)
            missing_plugins_values = [ep.value for ep in missing_plugins]
            logger.warning(
                f"The following classes do not have a corresponding information container: {missing_plugins_values}. They will not be loaded."
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
                    for info_type in [ModelInfo, ControllerInfo, WidgetInfo]
                ]
            ):
                logger.warning(
                    f"Loaded model info {info_ep.value} is not a subclass "
                    f"of any recognized model info class. "
                    f"Plugin will not be loaded."
                )
                continue
            base_class = plugin_ep.load()
            # the class key is the last part of the value
            model_key = plugin_ep.value.split(":")[-1]
            output_plugins[model_key] = Plugin(
                name=model_key, info=info_builder, base_class=base_class
            )

        return output_plugins
