from __future__ import annotations

import logging
from importlib import import_module
from importlib.metadata import entry_points
from importlib.resources import as_file, files
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Mapping
    from importlib.metadata import EntryPoints

__all__ = ["PluginError", "load_providers", "resolve"]

logger = logging.getLogger("redsun")

META_KEYS = frozenset({"plugin_name", "plugin_id"})

PLUGIN_GROUP = "redsun.plugins"


class PluginError(RuntimeError):
    """A configuration entry names a plugin, group or id that does not resolve."""


def resolve(entry: Mapping[str, Any], group: str) -> type | None:
    """Return the class a configuration entry names, or ``None``.

    An entry naming no plugin is not a plugin entry and yields ``None``; an
    entry naming one that cannot be resolved raises, because the alternative
    is an application that silently comes up missing a component.

    Parameters
    ----------
    entry : Mapping[str, Any]
        A configuration entry, carrying ``plugin_name`` and ``plugin_id``.
    group : str
        Manifest section to look in: ``devices``, ``presenters``, ``views`` or
        ``providers``.

    Raises
    ------
    PluginError
        If the plugin, the group, the id or the class path does not resolve.
    """
    if not META_KEYS <= entry.keys():
        return None
    return import_class(class_path(entry["plugin_name"], entry["plugin_id"], group))


def load_providers(config: Mapping[str, Any]) -> dict[str, type]:
    """Return the shared-service classes a configuration names, by entry name.

    Read from the ``providers`` section, so that a session assembled from a
    file gets a plugin's shared services without naming them in Python. A
    provider is an ordinary class: its constructor is filled from the session
    the way a component's is, and every method it marks with ``provides``
    registers a value under the type that method returns.

    Raises
    ------
    PluginError
        If an entry does not resolve, or names something that is not a class.
    """
    found: dict[str, type] = {}
    for name, entry in config.get("providers", {}).items():
        if not isinstance(entry, dict):
            continue
        cls = resolve(entry, "providers")
        if cls is None:
            continue
        if not isinstance(cls, type):
            raise PluginError(
                f"provider {name!r} resolves to {cls!r}, which is not a class"
            )
        found[name] = cls
    return found


def class_path(plugin_name: str, plugin_id: str, group: str) -> str:
    """Look up ``module:Class`` for *plugin_id* in *plugin_name*'s manifest."""
    manifests: EntryPoints = entry_points(group=PLUGIN_GROUP)
    plugin = next((e for e in manifests if e.name == plugin_name), None)
    if plugin is None:
        known = ", ".join(sorted(e.name for e in manifests)) or "none"
        raise PluginError(
            f"plugin {plugin_name!r} is not installed. Installed: {known}"
        )

    resource = files(plugin.name.replace("-", "_")) / plugin.value
    with as_file(resource) as path, open(path) as fh:
        manifest: dict[str, dict[str, str]] = yaml.safe_load(fh) or {}

    if group not in manifest:
        known = ", ".join(sorted(manifest)) or "none"
        raise PluginError(
            f"plugin {plugin_name!r} declares no {group!r} section. "
            f"Its sections: {known}"
        )
    items = manifest[group]
    if plugin_id not in items:
        known = ", ".join(sorted(items)) or "none"
        raise PluginError(
            f"plugin {plugin_name!r} declares no {group[:-1]} {plugin_id!r}. "
            f"Its {group}: {known}"
        )
    return items[plugin_id]


def import_class(class_path: str) -> type:
    """Import ``module:Class``."""
    module_name, _, class_name = class_path.partition(":")
    if not module_name or not class_name:
        raise PluginError(
            f"{class_path!r} is not a class path; expected 'module:ClassName'"
        )
    try:
        imported = getattr(import_module(module_name), class_name)
    except (ImportError, AttributeError) as e:
        raise PluginError(f"cannot import {class_path!r}: {e}") from e
    if not isinstance(imported, type):
        raise PluginError(f"{class_path!r} names {imported!r}, which is not a class")
    return imported
