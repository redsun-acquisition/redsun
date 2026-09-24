from __future__ import annotations

import logging
from functools import cache
from importlib import import_module
from typing import TYPE_CHECKING, Any

from .._manifest import PluginManifest, ServiceEntry, discover

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "PluginError",
    "installed",
    "load_providers",
    "manifest",
    "resolve",
    "service_entry",
]

logger = logging.getLogger("redsun")

META_KEYS = frozenset({"plugin_name", "plugin_id"})


class PluginError(RuntimeError):
    """A configuration entry names a plugin, group or id that does not resolve."""


def resolve(entry: Mapping[str, Any], group: str) -> type | None:
    """Return the class a configuration entry names, or ``None``.

    An entry naming no plugin is not a plugin entry and yields ``None``.

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

    An entry that does not resolve is logged and left out.
    """
    found: dict[str, type] = {}
    for name, entry in config.get("providers", {}).items():
        if not isinstance(entry, dict):
            continue
        try:
            cls = resolve(entry, "providers")
        except PluginError as e:
            logger.error("Failed to load provider '%s': %s", name, e)
            continue
        if cls is not None:
            found[name] = cls
    return found


def service_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Return the keywords a ``services`` entry gives, its plugin's included.

    An entry naming a plugin takes ``module`` and ``ready`` from the plugin's
    manifest, under anything the entry itself gives.

    Raises
    ------
    PluginError
        If the plugin does not resolve.
    """
    own = {k: v for k, v in entry.items() if k not in META_KEYS}
    if not META_KEYS <= entry.keys():
        return own
    listed = manifest_item(entry["plugin_name"], entry["plugin_id"], "services")
    assert isinstance(listed, ServiceEntry)
    return {**listed.model_dump(exclude_none=True), **own}


@cache
def installed() -> dict[str, PluginManifest]:
    """Return every installed manifest that validates, read once until cleared.

    Reading them scans every installed distribution, so a session reading
    many entries reads the manifests once. `Session.build` clears the cache
    before it reads the configuration, so a build sees plugins installed since
    the last one. A manifest that does not validate is logged and left out.
    """
    return discover()


def manifest(plugin_name: str) -> PluginManifest:
    """Return *plugin_name*'s manifest.

    Raises
    ------
    PluginError
        If the plugin is not installed, or its manifest was left out.
    """
    found = installed()
    if plugin_name not in found:
        known = ", ".join(sorted(found)) or "none"
        raise PluginError(
            f"plugin {plugin_name!r} is not installed, or its manifest is invalid. "
            f"Installed: {known}"
        )
    return found[plugin_name]


def manifest_item(plugin_name: str, plugin_id: str, group: str) -> str | ServiceEntry:
    """Return what *plugin_name*'s manifest lists as *plugin_id* under *group*.

    Raises
    ------
    PluginError
        If the plugin is not installed, or its manifest has no such entry.
    """
    items: dict[str, str | ServiceEntry] = getattr(manifest(plugin_name), group)
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
