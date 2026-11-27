"""Describe the keys a plugin's devices, presenters and views take."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Final, get_args

from pydantic import BaseModel, PydanticUserError, create_model
from pydantic.json_schema import PydanticJsonSchemaWarning

from redsun import __version__
from redsun.errors import PluginError

from ._config import DeviceEntry, PresenterEntry, ViewEntry
from ._manifest import survey
from ._reports import (
    FORMAT,
    Described,
    DescribedGroup,
    DescribeReport,
    Problem,
    SessionParameter,
)
from .session._base import HELD
from .session._factories import parameters_of
from .session._plugins import installed, resolve

if TYPE_CHECKING:
    from ._manifest import PluginManifest
    from .session._factories import Parameters

GROUPS: Final = get_args(DescribedGroup)
"""The groups of a manifest `describe_report` describes, in the order it lists them."""

ENTRY_MODELS: Final[dict[str, type[BaseModel]]] = {
    "devices": DeviceEntry,
    "presenters": PresenterEntry,
    "views": ViewEntry,
}
"""The session-file model of each group's entries, whose keys every entry takes."""


def describe_report(plugin_name: str, plugin_id: str | None = None) -> DescribeReport:
    """Return the keys each device, presenter and view of *plugin_name* takes.

    With *plugin_id*, only that entry is described.
    """
    # the classes are looked up in the plugins installed now, as a build does
    installed.cache_clear()
    found = next((f for f in survey() if f.name == plugin_name), None)
    if found is None or found.manifest is None:
        message = (
            found.problem
            if found is not None
            else f"no installed plugin is named {plugin_name!r}"
        )
        return report(
            plugin_name, [Problem(kind="manifest", where=plugin_name, message=message)]
        )
    entries = [
        (group, entry_id, listed)
        for group, entry_id, listed in listed_entries(found.manifest)
        if plugin_id in (None, entry_id)
    ]
    if plugin_id is not None and not entries:
        message = f"{plugin_name!r} lists no device, presenter or view {plugin_id!r}"
        where = f"{plugin_name}.{plugin_id}"
        return report(
            plugin_name, [Problem(kind="manifest", where=where, message=message)]
        )
    problems: list[Problem] = []
    components: list[Described] = []
    for group, entry_id, listed in entries:
        component, found_problems = described(plugin_name, group, entry_id, listed)
        components.append(component)
        problems.extend(found_problems)
    return report(plugin_name, problems, components)


def report(
    plugin_name: str,
    problems: list[Problem],
    components: list[Described] | None = None,
) -> DescribeReport:
    """Return a report of *plugin_name* holding *problems* and *components*."""
    return DescribeReport(
        redsun=__version__,
        format=FORMAT,
        problems=problems,
        plugin_name=plugin_name,
        components=components or [],
    )


def listed_entries(manifest: PluginManifest) -> list[tuple[str, str, str]]:
    """Return the group, id and class path of each entry `describe_report` describes."""
    return [
        (group, entry_id, listed)
        for group in GROUPS
        for entry_id, listed in sorted(getattr(manifest, group).items())
    ]


def described(
    plugin_name: str, group: str, plugin_id: str, listed: str
) -> tuple[Described, list[Problem]]:
    """Return the description of one entry, and the problems of its parameters."""
    record: dict[str, Any] = {"group": group, "plugin_id": plugin_id, "class": listed}
    try:
        cls = resolve(plugin_name, plugin_id, group)
        if cls is None:
            raise PluginError(f"{plugin_name!r} names no class for {plugin_id!r}")
        parameters = parameters_of(cls, HELD, device=group == "devices")
    except (PluginError, TypeError) as error:
        failed = Described.model_validate(
            {**record, "status": "failed", "reason": str(error)}
        )
        return failed, []
    problems = [
        Problem(kind="parameter", where=f"{plugin_id}.{name}", message=message)
        for name, message in parameters.problems.items()
    ]
    session = [
        SessionParameter(
            name=filled.name,
            type=filled.type,
            required=filled.required,
            file=filled.file,
        )
        for filled in parameters.filled
    ]
    try:
        schema = entry_schema(
            entry_model(cls, group, parameters),
            group,
            plugin_name,
            plugin_id,
            parameters,
        )
    except (PydanticUserError, TypeError, ValueError) as error:
        failed = Described.model_validate(
            {**record, "status": "failed", "reason": str(error), "session": session}
        )
        return failed, problems
    refused = parameters.refusal is not None
    component = Described.model_validate(
        {
            **record,
            "status": "failed" if refused else "passed",
            "schema": schema,
            "session": session,
            "reason": parameters.refusal,
        }
    )
    return component, problems


def entry_model(cls: type, group: str, parameters: Parameters) -> type[BaseModel]:
    """Return the model of an entry naming *cls*: the group's keys and the constructor's."""
    # mypy checks an unpacked dict against create_model's own keywords too
    fields: dict[str, Any] = dict(parameters.fields)
    model: type[BaseModel] = create_model(
        f"{cls.__name__}Entry", __base__=ENTRY_MODELS[group], **fields
    )
    return model


def entry_schema(
    model: type[BaseModel],
    group: str,
    plugin_name: str,
    plugin_id: str,
    parameters: Parameters,
) -> dict[str, Any]:
    """Return the JSON Schema of an entry *model* describes, as `redsun describe` prints it.

    The plugin keys are fixed to this entry. A model-type key the session may
    fill is not required. A required keyword of a device may also come from
    a service, through `services` or, for `prefix`, through `service`.
    """
    # a default pydantic cannot write as JSON is left out of the schema
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PydanticJsonSchemaWarning)
        schema = model.model_json_schema()
    schema.pop("description", None)
    properties = schema.setdefault("properties", {})
    properties["plugin_name"] = {"const": plugin_name}
    properties["plugin_id"] = {"const": plugin_id}
    from_file = {filled.name for filled in parameters.filled if filled.file}
    required = [key for key in schema.get("required", []) if key not in from_file]
    if group == "devices":
        keywords = [key for key in required if key in parameters.fields]
        required = [key for key in required if key not in keywords]
        if keywords:
            schema["allOf"] = [{"anyOf": alternatives(key)} for key in keywords]
    schema["required"] = ["plugin_name", "plugin_id", *required]
    schema["additionalProperties"] = parameters.open
    return schema


def alternatives(keyword: str) -> list[dict[str, Any]]:
    """Return the ways a device entry can give *keyword*: itself, or through a service."""
    ways: list[dict[str, Any]] = [
        {"required": [keyword]},
        {"required": ["services"], "properties": {"services": {"required": [keyword]}}},
    ]
    if keyword == "prefix":
        ways.append({"required": ["service"]})
    return ways
