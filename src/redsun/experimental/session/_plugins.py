from __future__ import annotations

import logging
from functools import cache
from importlib import import_module
from importlib.metadata import entry_points
from importlib.resources import as_file, files
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Mapping
    from importlib.metadata import EntryPoints

__all__ = ["PluginError", "load_providers", "manifest", "resolve", "service_entry"]

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
    listed = manifest_item(entry["plugin_name"], entry["plugin_id"], group)
    return import_class(str(listed))


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


def service_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Return the keywords a ``services`` entry gives, its plugin's included.

    An entry naming a plugin takes ``module`` and ``ready`` from the plugin's
    manifest, under anything the entry itself gives.

    Raises
    ------
    PluginError
        If the plugin does not resolve, or its entry is not a mapping.
    """
    own = {k: v for k, v in entry.items() if k not in META_KEYS}
    if not META_KEYS <= entry.keys():
        return own
    listed = manifest_item(entry["plugin_name"], entry["plugin_id"], "services")
    if not isinstance(listed, dict):
        raise PluginError(
            f"plugin {entry['plugin_name']!r} lists service "
            f"{entry['plugin_id']!r} as {listed!r}, not a mapping"
        )
    return {**listed, **own}


@cache
def manifest(plugin_name: str) -> dict[str, dict[str, Any]]:
    """Return *plugin_name*'s parsed manifest, read once until the cache is cleared.

    Looking a plugin up scans every installed distribution, so a session reading
    many entries of one plugin reads its manifest once. `Session.build` clears
    the cache before it reads the configuration, so a build sees plugins
    installed since the last one.

    Raises
    ------
    PluginError
        If the plugin is not installed.
    """
    manifests: EntryPoints = entry_points(group=PLUGIN_GROUP)
    plugin = next((e for e in manifests if e.name == plugin_name), None)
    if plugin is None:
        known = ", ".join(sorted(e.name for e in manifests)) or "none"
        raise PluginError(
            f"plugin {plugin_name!r} is not installed. Installed: {known}"
        )
    resource = files(plugin.name.replace("-", "_")) / plugin.value
    with as_file(resource) as path, open(path) as fh:
        found: dict[str, dict[str, Any]] = yaml.safe_load(fh) or {}
    return found


def manifest_item(plugin_name: str, plugin_id: str, group: str) -> Any:
    """Return what *plugin_name*'s manifest lists as *plugin_id* under *group*.

    Raises
    ------
    PluginError
        If the plugin is not installed, or its manifest has no such entry.
    """
    listed = manifest(plugin_name)
    if group not in listed:
        known = ", ".join(sorted(listed)) or "none"
        raise PluginError(
            f"plugin {plugin_name!r} declares no {group!r} section. "
            f"Its sections: {known}"
        )
    items = listed[group]
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
