"""What the `redsun` command reports, as models that print as JSON."""

from __future__ import annotations

from typing import Any, Final, Literal, get_args

from pydantic import BaseModel, Field

from redsun import __version__

from ._manifest import survey

FORMAT: Final = 1
"""The format of the reports, raised when a key is removed or changes meaning."""

DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
"""The JSON Schema dialect the schemas of the reports are written in."""

Group = Literal[
    "devices", "presenters", "views", "stacks", "providers", "services", "hooks"
]
"""A group of a plugin manifest."""

GROUPS: Final = get_args(Group)


class Problem(BaseModel, extra="forbid", frozen=True, use_attribute_docstrings=True):
    """Something a command found wrong."""

    kind: Literal["manifest"]
    """What the problem is about: `manifest`, a plugin manifest that was skipped."""

    where: str
    """What it was found in: for a manifest, the name of the plugin."""

    message: str
    """What is wrong, as `redsun` logs it."""


class Entry(BaseModel, extra="forbid", frozen=True, use_attribute_docstrings=True):
    """One entry of a plugin manifest."""

    group: Group
    """The group of the manifest the entry is listed under."""

    plugin_id: str
    """The id a session file gives as `plugin_id`."""

    class_path: str | None = Field(default=None, alias="class")
    """The class the entry names, as `module:ClassName`; absent for a service."""

    module: str | None = None
    """The module a service is run from; absent for every other group."""


class Plugin(BaseModel, extra="forbid", frozen=True, use_attribute_docstrings=True):
    """An installed plugin whose manifest loaded."""

    plugin_name: str
    """The name a session file gives as `plugin_name`."""

    distribution: str | None = None
    """The distribution that installs the plugin; absent when it is unknown."""

    version: str | None = None
    """The version of that distribution."""

    entries: list[Entry]
    """What the manifest lists, by group and then by id."""


class Report(BaseModel, extra="forbid", frozen=True, use_attribute_docstrings=True):
    """What every report of the `redsun` command starts with."""

    redsun: str
    """The version of `redsun` that wrote the report."""

    format: int
    """The format of the report, raised when a key is removed or changes meaning."""

    problems: list[Problem]
    """What the command found wrong, empty when nothing is."""

    def to_json(self) -> str:
        """Return the report as the JSON the command prints."""
        return self.model_dump_json(by_alias=True, exclude_none=True, indent=2)


class PluginsReport(Report, frozen=True):
    """The installed plugins and what each one offers."""

    plugins: list[Plugin]
    """The plugins whose manifest loaded, in the order they were found."""


def plugins_report() -> PluginsReport:
    """Return the installed plugins, with a problem for each manifest that was skipped."""
    plugins = []
    problems = []
    for found in survey():
        if found.manifest is None:
            problems.append(
                Problem(kind="manifest", where=found.name, message=found.problem)
            )
            continue
        entries = []
        for group in GROUPS:
            for plugin_id, listed in sorted(getattr(found.manifest, group).items()):
                if group == "services":
                    entry = Entry(
                        group=group, plugin_id=plugin_id, module=listed.module
                    )
                else:
                    entry = Entry.model_validate(
                        {"group": group, "plugin_id": plugin_id, "class": listed}
                    )
                entries.append(entry)
        plugins.append(
            Plugin(
                plugin_name=found.name,
                distribution=found.distribution,
                version=found.version,
                entries=entries,
            )
        )
    return PluginsReport(
        redsun=__version__, format=FORMAT, problems=problems, plugins=plugins
    )


def report_schemas() -> dict[str, dict[str, Any]]:
    """Return the JSON Schema of each report, by the name of its file."""
    reports: dict[str, type[Report]] = {"plugins-report": PluginsReport}
    return {
        name: {
            "$schema": DIALECT,
            **report.model_json_schema(by_alias=True, mode="serialization"),
        }
        for name, report in reports.items()
    }
