"""The plugin manifest a bundle registers under the `redsun.plugins` group."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import entry_points
from importlib.resources import as_file, files
from typing import TYPE_CHECKING, Annotated, Final

import yaml
from pydantic import AfterValidator, BaseModel, ValidationError

from redsun.services import STARTUP_TIMEOUT, STOP_TIMEOUT

from .services._service import ArgValue

if TYPE_CHECKING:
    from collections.abc import Callable
    from importlib.metadata import EntryPoint

    from pydantic_core import ErrorDetails

logger = logging.getLogger("redsun")

ENTRY_POINT_GROUP: Final = "redsun.plugins"
OWN_PLUGIN: Final = "redsun"
"""The plugin holding what `redsun` itself ships, short hook names included."""


def class_path(value: str) -> str:
    """Refuse text that does not name a class as `module:ClassName`."""
    if not re.fullmatch(r"[A-Za-z_][\w.]*:[A-Za-z_]\w*", value):
        raise ValueError(f"{value!r} is not a class path; expected 'module:ClassName'")
    return value


ClassPath = Annotated[str, AfterValidator(class_path)]
"""A class named as `module:ClassName`, imported only when a session uses it."""


def import_class(path: str) -> type:
    """Import the class *path* names as `module:ClassName`.

    Raises
    ------
    ImportError
        If the module cannot be imported, or holds no such name.
    TypeError
        If the name is not a class.
    """
    module_name, _, class_name = path.partition(":")
    try:
        imported = getattr(import_module(module_name), class_name)
    except AttributeError as e:
        raise ImportError(str(e)) from e
    if not isinstance(imported, type):
        raise TypeError(f"it names {imported!r}, which is not a class")
    return imported


def message_of(problem: ErrorDetails) -> str:
    """Return what a problem says, without the prefix pydantic puts on a raised error."""
    if problem["type"] == "value_error":
        return str(problem["ctx"]["error"])
    return problem["msg"]


def problem_lines(
    error: ValidationError,
    locate: Callable[[list[str | int]], list[str | int]] | None = None,
) -> list[str]:
    """Say each problem of *error* as `section.key: what`.

    *locate* rewrites a problem's location first, for a model that holds
    something differently from the file it was read from.
    """
    lines = []
    for problem in error.errors():
        loc = list(problem["loc"])
        if locate is not None:
            loc = locate(loc)
        where = ".".join(str(part) for part in loc) or "(top level)"
        lines.append(f"{where}: {message_of(problem)}")
    return lines


class ServiceEntry(BaseModel, extra="forbid", use_attribute_docstrings=True):
    """How a manifest launches a service; a session file may override any of it."""

    module: str
    """Module run as `python -m <module>`."""

    args: list[str] | dict[str, ArgValue] = []
    """Arguments after the module: a list, or options mapped to their values."""

    ready: str | None = None
    """Line the service prints once it serves."""

    startup_timeout: float = STARTUP_TIMEOUT
    """Seconds the session waits for the readiness line."""

    stop_timeout: float = STOP_TIMEOUT
    """Seconds each stop step waits."""


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

    stacks: dict[str, ClassPath] = {}
    """Stack classes by id."""

    providers: dict[str, ClassPath] = {}
    """Classes registering shared values, by id."""

    services: dict[str, ServiceEntry] = {}
    """Services by id."""

    hooks: dict[str, ClassPath] = {}
    """Hook provider classes by the short name a session file gives them."""


def discover() -> dict[str, PluginManifest]:
    """Read every installed manifest, by entry point name.

    A manifest that cannot be read, or does not validate, is logged with its
    file and every error, and left out whole.
    """
    manifests: dict[str, PluginManifest] = {}
    for found in survey():
        if found.manifest is None:
            logger.error('Plugin "%s" %s', found.name, found.problem)
        else:
            manifests[found.name] = found.manifest
    return manifests


@dataclass(frozen=True, slots=True)
class Found:
    """One entry point of the `redsun.plugins` group, and what reading it gave."""

    name: str
    """The entry point's name, which a session file gives as `plugin_name`."""

    distribution: str | None
    """The distribution registering the entry point, `None` when it is unknown."""

    version: str | None
    """The version of that distribution."""

    manifest: PluginManifest | None
    """The manifest, `None` when it was skipped."""

    problem: str
    """Why the manifest was skipped, empty when it was not."""


def survey() -> list[Found]:
    """Read the manifest of every installed plugin, the skipped ones included.

    A manifest that cannot be read, does not validate, names itself otherwise
    than its entry point or has a `hooks` section is skipped, and the
    `problem` of its entry says which.
    """
    found = []
    for plugin in entry_points(group=ENTRY_POINT_GROUP):
        manifest, problem = read_manifest(plugin.name, plugin.value)
        distribution, version = installed_as(plugin)
        found.append(
            Found(
                name=plugin.name,
                distribution=distribution,
                version=version,
                manifest=manifest,
                problem=problem,
            )
        )
    return found


def installed_as(plugin: EntryPoint) -> tuple[str | None, str | None]:
    """Return the name and version of the distribution registering *plugin*.

    Both are `None` when the entry point names no distribution, or when its
    metadata cannot be read: a session still builds with such a plugin.
    """
    if plugin.dist is None:
        return None, None
    try:
        return plugin.dist.name, plugin.dist.version
    except (KeyError, TypeError, OSError):
        return None, None


def read_manifest(name: str, value: str) -> tuple[PluginManifest | None, str]:
    """Return the manifest the entry point *name* gives as *value*, or why it is skipped."""
    try:
        resource = files(name.replace("-", "_")) / value
        with as_file(resource) as path, open(path) as f:
            manifest = PluginManifest.model_validate(yaml.safe_load(f) or {})
    except (ImportError, OSError, yaml.YAMLError) as e:
        return None, f"manifest {value} could not be read and was skipped: {e}"
    except ValidationError as e:
        lines = "\n".join(f"  {line}" for line in problem_lines(e))
        return None, f"manifest {path} is invalid and was skipped:\n{lines}"
    if manifest.name is not None and manifest.name != name:
        return None, f'manifest {path} names itself "{manifest.name}" and was skipped.'
    if manifest.hooks and name != OWN_PLUGIN:
        return None, (
            f"manifest {value} has a hooks section and was skipped: "
            "only redsun ships short hook names. Name the provider by its "
            "class path, module:ClassName, in the session."
        )
    return manifest, ""
