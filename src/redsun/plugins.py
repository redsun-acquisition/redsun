from __future__ import annotations

import logging
from importlib import import_module

try:
    from importlib.metadata import EntryPoints, entry_points
except ImportError:
    from importlib_metadata import EntryPoints, entry_points  # type: ignore

from importlib.metadata import EntryPoints, entry_points
from pathlib import Path
from typing import Any, Final, Literal, TypedDict, TypeVar, Union

import yaml
from sunflare.config import (
    AcquisitionEngineTypes,
    ControllerInfo,
    ControllerInfoProtocol,
    FrontendTypes,
    ModelInfo,
    ModelInfoProtocol,
    RedSunSessionInfo,
    WidgetInfo,
    WidgetInfoProtocol,
)
from sunflare.controller import ControllerProtocol
from sunflare.model import ModelProtocol
from sunflare.view import WidgetProtocol
from typing_extensions import Generic, NamedTuple

logger = logging.getLogger("redsun")


class PluginInfoDict(TypedDict):
    """A support typed dictionary for backend information models.

    Parameters
    ----------
    models : ``dict[str, ModelInfoProtocol]``
        Dictionary of model informations.
    controllers : ``dict[str, ControllerInfo]``
        Dictionary of controller informations.
    widgets : ``dict[str, WidgetInfo]``
        Dictionary of widget informations.
    """

    models: dict[str, ModelInfoProtocol]
    controllers: dict[str, ControllerInfoProtocol]
    widgets: dict[str, WidgetInfoProtocol]


class PluginTypeDict(TypedDict):
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


T = TypeVar("T")  # generic type
IC = TypeVar("IC")  # info class
PC = TypeVar("PC")  # plugin class


class Plugin(NamedTuple, Generic[IC, PC]):
    """A named tuple representing the elements required to identify and load a plugin.

    Parameters
    ----------
    name : ``str``
        The name of the plugin.
    info : ``IC``
        The information class for the plugin.
    base_class : ``type[PC]``
        The base class for the plugin.
    """

    name: str
    info: IC
    base_class: type[PC]


# helper typing
PluginInfo = Union[ModelInfoProtocol, ControllerInfoProtocol, WidgetInfoProtocol]
PluginType = Union[ModelProtocol, ControllerProtocol, WidgetProtocol]
ManifestItems = dict[str, dict[str, str]]

# constants
FALLBACK_INFO: Final[dict[str, Any]] = {
    "models": ModelInfo,
    "controllers": ControllerInfo,
    "widgets": WidgetInfo,
}

PLUGIN_GROUPS = Literal["models", "controllers", "widgets"]


def load_configuration(
    config_path: str,
) -> tuple[RedSunSessionInfo, PluginTypeDict]:
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
    ``tuple[RedSunSessionInfo, PluginTypeDict]``
        Redsun instance configuration and class types to build.
    """
    config = RedSunSessionInfo.load_yaml(config_path)

    session = config.pop("session", "Redsun")
    try:
        engine = AcquisitionEngineTypes(config.pop("engine"))
        frontend = FrontendTypes(config.pop("frontend"))
    except KeyError as e:
        raise KeyError(f"Configuration file {config_path} is missing the key {e}.")

    plugin_types = PluginTypeDict(models={}, controllers={}, widgets={})
    plugins_info = PluginInfoDict(models={}, controllers={}, widgets={})

    available_manifests = entry_points(group="redsun.plugins")

    groups: list[PLUGIN_GROUPS] = ["models", "controllers", "widgets"]

    for group in groups:
        if group not in config.keys():
            logger.debug(
                "Group %s not found in the configuration file. Skipping", group
            )
            continue
        plugins = _load_plugins(
            group_cfg=config[group],
            group=group,
            available_manifests=available_manifests,
        )
        for p in plugins:
            # it's too hard to explain to the
            # type checker which is the actual
            # type of p.info and p.base_class;
            # we know it's correct, so we'll just
            # ignore the type checker here
            plugin_types[group][p.name] = p.base_class  # type: ignore[assignment]
            plugins_info[group][p.name] = p.info  # type: ignore[assignment]

    session_container = RedSunSessionInfo(
        session=session,
        engine=engine,
        frontend=frontend,
        models=plugins_info["models"],
        controllers=plugins_info["controllers"],
        widgets=plugins_info["widgets"],
    )

    return (session_container, plugin_types)


def _load_plugins(
    *, group_cfg: dict[str, Any], group: str, available_manifests: EntryPoints
) -> list[Plugin[PluginInfo, PluginType]]:
    """Load a plugin group.

    Parameters
    ----------
    group_cfg : ``dict[str, Any]``
        Configuration read from the YAML file for given ``group``.
    group : ``str``
        The group of plugins to load.
    available_manifests : ``EntryPoints``
        The available entry points.

    Returns
    -------
    ``list[Plugin[PluginInfo, PluginType]]``
        A list of loaded plugins for the group.
    """
    plugins: list[Plugin[PluginInfo, PluginType]] = []

    for name, info in group_cfg.items():
        # inspect the configuration;
        # grab the plugin name and id
        plugin_name = info["plugin_name"]
        plugin_id = info["plugin_id"]

        iterator = (entry for entry in available_manifests if entry.name == plugin_name)

        # check if the plugin is available in the entry points
        plugin = next(iterator, None)
        if plugin is not None:
            # load the manifest file
            manifest_path = Path(plugin.load()).resolve()
            with open(manifest_path, "r") as f:
                # read the manifest for the current group
                manifest: dict[str, ManifestItems] = yaml.safe_load(f)
                items = manifest[group]
                if plugin_id not in items.keys():
                    # plugin id not found in the manifest;
                    # log the error and continue
                    logger.error(
                        f'Plugin "{plugin_name}" does not contain the id "{plugin_id}".'
                    )
                    continue
                item = items[plugin_id]
                try:
                    # retrieve the class definition
                    class_item_module, class_item_type = item["class"].split(":")
                    imported_class = getattr(
                        import_module(class_item_module), class_item_type
                    )
                    acceptable = _check_import(imported_class, group)
                    if not acceptable:
                        logger.error(
                            f"{imported_class} exists, but does not implement any known protocol."
                        )
                        continue
                except KeyError:
                    # couldn't load the class definition;
                    # ditch the plugin and log the error
                    logger.error(
                        f'Plugin id "{plugin_id}" of "{name}" does not contain the class key. Skipping.'
                    )
                    continue
                try:
                    # get the information class
                    info_item_module, info_item_type = item["info"].split(":")
                    imported_info = getattr(
                        import_module(info_item_module), info_item_type
                    )
                except KeyError:
                    # fallback to default info class
                    imported_info = FALLBACK_INFO[group]
                    logger.debug(
                        f'Plugin "{plugin_name}" does not contain the info key. Falling back to default info class.'
                    )

                # add the plugin to the dictionary
                imported_info_obj = imported_info(**info)
                plugins.append(
                    Plugin(name=name, info=imported_info_obj, base_class=imported_class)
                )
        else:
            logger.error(f'Plugin "{plugin_name}" not found in the installed plugins.')

    return plugins


def _check_import(imported_class: type[T], group: str) -> bool:
    """Check if the imported class implements the correct protocol.

    Parameters
    ----------
    imported_class : ``type[T]``
        The imported class to check.
    group : ``str``
        The group to check the class against.

    Returns
    -------
    ``bool``
        True if the class implements the correct protocol; False otherwise.
    """
    if group == "models":
        return isinstance(imported_class, ModelProtocol)
    elif group == "controllers":
        return isinstance(imported_class, ControllerProtocol)
    elif group == "widgets":
        return isinstance(imported_class, WidgetProtocol)
    # if we fall here, we have a problem; but we shouldn't
    raise ValueError(f"Unknown group {group}.")  # pragma: no cover
