from __future__ import annotations

import logging
from functools import cache
from typing import TYPE_CHECKING, Any

from .._manifest import PluginManifest, ServiceEntry, discover, import_class

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .._config import ComponentEntry

__all__ = [
    "PluginError",
    "installed",
    "load_providers",
    "manifest",
    "resolve",
    "service_entry",
]

logger = logging.getLogger("redsun")


class PluginError(RuntimeError):
    """A configuration entry names a plugin, group or id that does not resolve."""


def resolve(plugin_name: str | None, plugin_id: str | None, group: str) -> type | None:
    """Return the class a configuration entry names, or ``None``.

    An entry naming no plugin is not a plugin entry and yields ``None``.

    Parameters
    ----------
    plugin_name : str | None
        The entry's ``plugin_name``, ``None`` when it gives none.
    plugin_id : str | None
        The entry's ``plugin_id``, ``None`` when it gives none.
    group : str
        Manifest section to look in: ``devices``, ``presenters``, ``views`` or
        ``providers``.

    Raises
    ------
    PluginError
        If the plugin, the group, the id or the class path does not resolve.
    """
    if plugin_name is None or plugin_id is None:
        return None
    listed = str(manifest_item(plugin_name, plugin_id, group))
    try:
        return import_class(listed)
    except (ImportError, TypeError) as e:
        raise PluginError(f"cannot import {listed!r}: {e}") from e


def load_providers(providers: Mapping[str, Any]) -> dict[str, type]:
    """Return the shared-service classes a ``providers`` section names, by entry name.

    A session assembled from a file gets a plugin's shared services this way,
    without naming them in Python. A provider is an ordinary class: its
    constructor is filled from the session the way a component's is, and every
    method it marks with ``provides`` registers a value under the type that
    method returns.

    An entry that does not resolve is logged and left out.
    """
    found: dict[str, type] = {}
    for name, entry in providers.items():
        if not isinstance(entry, dict):
            continue
        try:
            cls = resolve(entry.get("plugin_name"), entry.get("plugin_id"), "providers")
        except PluginError as e:
            logger.error("Failed to load provider '%s': %s", name, e)
            continue
        if cls is not None:
            found[name] = cls
    return found


def service_entry(entry: ComponentEntry) -> dict[str, Any]:
    """Return the keywords a ``services`` entry gives, its plugin's included.

    An entry naming a plugin takes ``module``, ``args``, ``ready`` and
    ``stop_timeout`` from the plugin's manifest, under anything the entry
    itself gives.

    Raises
    ------
    PluginError
        If the plugin does not resolve.
    """
    own = dict(entry.model_extra or {})
    if entry.plugin_name is None or entry.plugin_id is None:
        return own
    listed = manifest_item(entry.plugin_name, entry.plugin_id, "services")
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
