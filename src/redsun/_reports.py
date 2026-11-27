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
"""The groups, in the order a report lists them."""

Status = Literal["passed", "failed", "undecided"]
"""The outcome of a check: certain to work, certain to fail, or not knowable without a build."""

DescribedGroup = Literal["devices", "presenters", "views"]
"""The groups of a manifest whose components `redsun describe` describes."""

SKIPPED: Final = (
    "what a constructor checks itself",
    "what setup does",
    "members of a SignalGroup",
    "placements a view gives through a property",
    "services and device connections, which never start",
)
"""What a check without a build cannot see, as `CheckReport.skipped` lists it."""


class Problem(BaseModel, frozen=True, use_attribute_docstrings=True):
    """Something a command found wrong."""

    kind: Literal["manifest", "value", "session", "parameter"]
    """What the problem is about.

    `manifest` is a plugin manifest that was skipped, or a plugin or entry
    that was not found; `value` a value of a session file that is refused,
    or that breaks the type or the limits its class declares;
    `session` a session that cannot be made or read at all; and `parameter` a
    constructor parameter that cannot be described.
    """

    where: str
    """What it was found in: for a manifest, the name of the plugin; for a value, its key path; for a session, the files."""

    message: str
    """What is wrong, as `redsun` logs it."""


class Entry(BaseModel, frozen=True, use_attribute_docstrings=True):
    """One entry of a plugin manifest."""

    group: Group
    """The group of the manifest the entry is listed under."""

    plugin_id: str
    """The id a session file gives as `plugin_id`."""

    class_path: str | None = Field(default=None, alias="class")
    """The class the entry names, as `module:ClassName`; absent for a service."""

    module: str | None = None
    """The module a service is run from; absent for every other group."""


class Plugin(BaseModel, frozen=True, use_attribute_docstrings=True):
    """An installed plugin whose manifest loaded."""

    plugin_name: str
    """The name a session file gives as `plugin_name`."""

    distribution: str | None = None
    """The distribution that installs the plugin; absent when it is unknown."""

    version: str | None = None
    """The version of that distribution."""

    entries: list[Entry]
    """What the manifest lists, by group and then by id."""


class Report(BaseModel, frozen=True, use_attribute_docstrings=True):
    """What every report of the `redsun` command starts with."""

    redsun: str
    """The version of `redsun` that wrote the report."""

    format: int
    """The value of `FORMAT` when the report was written."""

    problems: list[Problem]
    """What the command found wrong, empty when nothing is."""

    def to_json(self) -> str:
        """Return the report as the JSON the command prints."""
        return self.model_dump_json(by_alias=True, exclude_none=True, indent=2)


class Component(BaseModel, frozen=True, use_attribute_docstrings=True):
    """One declared component, service or hook provider, and what a check found."""

    name: str
    """The name the session declares it under."""

    group: Group
    """The section of the session file it belongs to."""

    plugin_name: str | None = None
    """The plugin its entry names; absent for a class the session declares in code."""

    plugin_id: str | None = None
    """The id of its entry in that plugin's manifest."""

    class_path: str | None = Field(default=None, alias="class")
    """Its class, as `module:ClassName`; absent when it could not be found."""

    status: Status
    """Whether it would be built."""

    reason: str | None = None
    """Why it failed, or why the check could not decide."""


class Lookup(BaseModel, frozen=True, use_attribute_docstrings=True):
    """One name the session file looks up, and what a check found."""

    section: Literal["layout", "wiring", "pairs", "stacks"]
    """The section of the session file the name is in."""

    name: str
    """The name as the section writes it, such as `ctrl.sig_moved -> panel.show`."""

    status: Status
    """Whether the name would be found."""

    reason: str | None = None
    """Why it failed, or why the check could not decide."""


class CheckReport(Report, frozen=True):
    """Whether a session file would build, found without building it."""

    components: list[Component]
    """Each declared component, service and hook provider."""

    lookups: list[Lookup]
    """Each name in `layout`, `wiring`, `pairs` and the stacks."""

    skipped: list[str]
    """What the check could not look at."""


class PluginsReport(Report, frozen=True):
    """The installed plugins and what each one offers."""

    plugins: list[Plugin]
    """The plugins whose manifest loaded, in the order they were found."""


class SessionParameter(BaseModel, frozen=True, use_attribute_docstrings=True):
    """A constructor parameter the session fills by its type."""

    name: str
    """The parameter's name."""

    type: str
    """Its type, as text: `module:Name` for a class, the `typing` form otherwise."""

    required: bool
    """Whether it has no default, so the build fails when nothing fills it."""

    file: bool
    """Whether a session file may give it instead."""


class Described(BaseModel, frozen=True, use_attribute_docstrings=True):
    """One device, presenter or view of a manifest, and the keys its entry takes."""

    group: DescribedGroup
    """The group of the manifest it is listed under."""

    plugin_id: str
    """The id a session file gives as `plugin_id`."""

    class_path: str = Field(alias="class")
    """The class the manifest names, as `module:ClassName`."""

    status: Literal["passed", "failed"]
    """Whether the session can build it, as far as its constructor tells."""

    json_schema: dict[str, Any] | None = Field(default=None, alias="schema")
    """The JSON Schema of the keys its session-file entry takes.

    Absent when its class cannot be imported or its signature read.
    """

    session: list[SessionParameter] = []
    """The constructor parameters the session fills by their type."""

    reason: str | None = None
    """Why it failed."""


class DescribeReport(Report, frozen=True):
    """The keys each device, presenter and view of a plugin takes."""

    plugin_name: str
    """The plugin described."""

    components: list[Described]
    """Its devices, presenters and views, in the order of the manifest's groups."""


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
    reports: dict[str, type[Report]] = {
        "check-report": CheckReport,
        "plugins-report": PluginsReport,
        "describe-report": DescribeReport,
    }
    return {
        name: {
            "$schema": DIALECT,
            **report.model_json_schema(by_alias=True, mode="serialization"),
        }
        for name, report in reports.items()
    }
