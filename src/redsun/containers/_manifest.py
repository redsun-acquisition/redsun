"""The plugin manifest a bundle registers under the ``redsun.plugins`` group."""

from __future__ import annotations

import logging
import re
from importlib.metadata import entry_points
from importlib.resources import as_file, files
from typing import Annotated, Final

import yaml
from pydantic import AfterValidator, BaseModel, ValidationError

logger = logging.getLogger("redsun")

ENTRY_POINT_GROUP: Final = "redsun.plugins"


def class_path(value: str) -> str:
    """Refuse text that does not name a class as ``module:ClassName``."""
    if not re.fullmatch(r"[A-Za-z_][\w.]*:[A-Za-z_]\w*", value):
        raise ValueError(f"{value!r} is not a class path; expected 'module:ClassName'")
    return value


ClassPath = Annotated[str, AfterValidator(class_path)]
"""A class named as ``module:ClassName``, imported only when a session uses it."""


class ServiceEntry(BaseModel, extra="forbid", use_attribute_docstrings=True):
    """How a manifest launches a service; a session file may override any of it."""

    module: str
    """Module run as ``python -m <module>``."""

    args: list[str] = []
    """Arguments after the module."""

    ready: str | None = None
    """Line the service prints once it serves."""

    stop_timeout: float | None = None
    """Seconds each stop step waits; the service's own default if unset."""


class PluginManifest(BaseModel, extra="forbid", use_attribute_docstrings=True):
    """What a bundle ships, by group, each entry under the id a session names."""

    name: str | None = None
    """The entry point's name; the manifest is left out if it differs."""

    schema_version: float | None = None
    """Version of this manifest format."""

    devices: dict[str, ClassPath] = {}
    """Device classes by id."""

    presenters: dict[str, ClassPath] = {}
    """Presenter classes by id."""

    views: dict[str, ClassPath] = {}
    """View classes by id."""

    services: dict[str, ServiceEntry] = {}
    """Services by id."""


def discover() -> dict[str, PluginManifest]:
    """Read every installed manifest, by entry point name.

    A manifest that cannot be read, or does not validate, is logged with its
    file and every error, and left out whole: one bundle's mistake must not
    fail the sessions that do not use it.
    """
    manifests: dict[str, PluginManifest] = {}
    for plugin in entry_points(group=ENTRY_POINT_GROUP):
        try:
            resource = files(plugin.name.replace("-", "_")) / plugin.value
            with as_file(resource) as path, open(path) as f:
                manifest = PluginManifest.model_validate(yaml.safe_load(f) or {})
        except (ImportError, OSError, yaml.YAMLError) as e:
            logger.error(
                'Plugin "%s" manifest %s could not be read and was skipped: %s',
                plugin.name,
                plugin.value,
                e,
            )
            continue
        except ValidationError as e:
            logger.error(
                'Plugin "%s" manifest %s is invalid and was skipped:\n%s',
                plugin.name,
                path,
                "\n".join(
                    f"  {'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                    for error in e.errors()
                ),
            )
            continue
        if manifest.name is not None and manifest.name != plugin.name:
            logger.error(
                'Plugin "%s" manifest %s names itself "%s" and was skipped.',
                plugin.name,
                path,
                manifest.name,
            )
            continue
        manifests[plugin.name] = manifest
    return manifests
