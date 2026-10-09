"""Configuration sources, and the rules for laying one over another."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from contextlib import suppress
from difflib import get_close_matches
from importlib.metadata import entry_points
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Final,
    TypeAlias,
    TypeGuard,
    cast,
)

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Discriminator,
    Field,
    ModelWrapValidatorHandler,
    Tag,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from redsun.errors import ConfigurationError
from redsun.services._transports import TRANSPORT_KEY, TRANSPORTS, transport_of
from redsun.view import Column, Row, Tabs, WindowLayout

from ._hooks import HookGroup, group_hook_entries
from ._manifest import problem_lines
from .view._layout import layout_problems, split_problems, tabs_problems

if TYPE_CHECKING:
    from collections.abc import Collection
    from importlib.metadata import EntryPoint

    from pydantic_core import InitErrorDetails

    from .view._layout import Node

Source: TypeAlias = str | Path | Mapping[str, Any]
"""One configuration source: a path to a YAML file, or a mapping in hand."""

logger = logging.getLogger("redsun")

__all__ = [
    "COMPONENT_SECTIONS",
    "EMPTY_AS_MAPPING",
    "IDENTITY_KEYS",
    "PLUGIN_KEYS",
    "SCHEMA_VERSIONS",
    "CatalogConfig",
    "ComponentEntry",
    "DeviceEntry",
    "SessionFile",
    "Source",
    "StorageConfig",
    "as_sources",
    "label",
    "load",
    "merge_config",
    "read",
    "refuse_identity_conflict",
    "session_file_schema",
    "validate_session",
]

COMPONENT_SECTIONS: Final = frozenset({"services", "devices", "presenters", "views"})
"""The configuration sections whose entries are a component's constructor call."""

REPLACED_WHOLE: Final = frozenset({"layout"})
"""Sections a later source replaces whole rather than merging into the earlier one."""

SCHEMA_VERSIONS: Final = (1.0,)
"""The session file schema versions this redsun reads."""

PLUGIN_KEYS: Final = ("plugin_name", "plugin_id")
"""The keys naming the plugin a component comes from."""

EMPTY_AS_MAPPING: Final = frozenset(
    {"metadata", "services", "devices", "presenters", "views", "wiring"}
)
"""Sections a file may write empty, read as an empty mapping."""

IDENTITY_KEYS: Final = ("schema_version", "frontend")
"""Keys naming what kind of session this is, which every layered source must agree on.

On every other key a later source overrides an earlier one. `session` is not
among them, so laying `{"session": "run-2"}` over a shared file renames the
session.
"""

FRONTEND_GROUP: Final = "redsun.frontends"
"""The entry point group naming the session class of each frontend."""


def frontends() -> dict[str, EntryPoint]:
    """Return the registered frontends, by the name a session file gives."""
    return {entry.name: entry for entry in entry_points(group=FRONTEND_GROUP)}


def as_sources(declared: Source | Sequence[Source] | None) -> list[Source]:
    """Return *declared* as the sequence of sources it stands for.

    One source is a sequence of one. A string is a path rather than the
    sequence of characters it also is, and a mapping is a source rather than a
    sequence of its keys.
    """
    if declared is None:
        return []
    if isinstance(declared, (str, Path, Mapping)):
        return [declared]
    return list(declared)


def read(source: Source) -> dict[str, Any]:
    """Read one configuration source into a mapping.

    A string or a path names a YAML file; a mapping is already the answer and
    is copied so that laying another source over it cannot reach the caller's.

    Raises
    ------
    TypeError
        If the file's top level is not a mapping.
    """
    if not isinstance(source, (str, Path)):
        return dict(source)
    with open(source) as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError(
            f"Expected a YAML mapping at top level in {source}, got "
            f"{type(data).__name__}"
        )
    return data


def label(source: Source) -> str:
    """Name *source* as an error message should refer to it."""
    if isinstance(source, (str, Path)):
        return str(source)
    return "an inline mapping"


def merge_config(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Return *base* with *overlay* laid over it, merging nested mappings.

    A key present in both is taken from *overlay* unless both values are
    mappings, which merge in turn. Anything that is not a mapping - a list, a
    scalar - is replaced rather than combined.

    A component entry is the exception: under `services`, `devices`,
    `presenters` and `views` the section merges by component name, but a
    component *named* in *overlay* is taken from it whole. A `layout` section
    is replaced whole: two layout trees have no single obvious merge.
    """
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if key in REPLACED_WHOLE or not (
            isinstance(current, dict) and isinstance(value, dict)
        ):
            merged[key] = value
        elif key in COMPONENT_SECTIONS:
            for shadowed in current.keys() & value.keys():
                logger.debug(
                    "Component '%s' in '%s' is taken from a later configuration "
                    "source, replacing the entry under it",
                    shadowed,
                    key,
                )
            # an entry is a constructor's keyword arguments, not a tree of
            # settings, so the last source naming a component owns them all
            merged[key] = {**current, **value}
        else:
            merged[key] = merge_config(current, value)
    return merged


def refuse_identity_conflict(
    data: Mapping[str, Any], overlay: Mapping[str, Any], source: Source
) -> None:
    """Refuse a source that contradicts what an earlier one said the session is.

    The transport its services speak is part of that identity, although it
    sits under `services`: every service of a session speaks the one it
    names.

    Raises
    ------
    ValueError
        If *overlay* gives a different value for a key naming the session's
        identity rather than its content.
    """
    for key in IDENTITY_KEYS:
        if key in data and key in overlay and data[key] != overlay[key]:
            raise ValueError(
                f"Configuration source {label(source)} sets {key}={overlay[key]!r}, "
                f"which contradicts {data[key]!r} from a source layered under it. "
                f"{key} names what kind of session this is, so every source must "
                f"agree on it."
            )
    under, over = transport_of(data), transport_of(overlay)
    if under is not None and over is not None and under != over:
        raise ValueError(
            f"Configuration source {label(source)} sets {TRANSPORT_KEY}={over!r} "
            f"under services, which contradicts {under!r} from a source layered "
            f"under it. Every service of a session speaks the same transport, so "
            f"every source must agree on it."
        )


def is_list_like(value: object) -> TypeGuard[Sequence[Any]]:
    """Tell a list or tuple from a string, a mapping or a scalar."""
    return isinstance(value, Sequence) and not isinstance(value, str)


def pairs_joined(earlier: Sequence[Any], later: Sequence[Any]) -> list[Any]:
    """Join two sequences of pairs as lists, dropping a pair already present."""
    joined: list[Any] = []
    for pair in (*earlier, *later):
        pair = list(pair) if is_list_like(pair) else pair
        if pair not in joined:
            joined.append(pair)
    return joined


def load(
    declared: Source | Sequence[Source] | None,
    required: Collection[str] = frozenset(),
) -> dict[str, Any]:
    """Read what *declared* names in order, laying each over the last.

    One source or several, so a caller with a single file hands it over as it
    is. *required* is checked against the merged mapping rather than against
    each source, so a source layered under another may carry a fragment.

    Raises
    ------
    ValueError
        If two sources disagree about the session's identity.
    KeyError
        If the merged mapping is missing a required key.
    """
    ordered = as_sources(declared)
    data: dict[str, Any] = {}
    for source in ordered:
        overlay = read(source)
        refuse_identity_conflict(data, overlay, source)
        earlier, later = data.get("pairs"), overlay.get("pairs")
        data = merge_config(data, overlay)
        if is_list_like(earlier) and (later is None or is_list_like(later)):
            data["pairs"] = pairs_joined(earlier, later or ())
    missing = set(required) - data.keys()
    if missing:
        named = ", ".join(label(source) for source in ordered) or "no sources"
        raise KeyError(
            f"Configuration ({named}) is missing required keys: "
            f"{', '.join(sorted(missing))}"
        )
    return data


def problems_of(error: ValidationError, data: Mapping[str, Any]) -> list[str]:
    """Say each problem as `section.key: what`, a hook entry by its hook points.

    The model holds hook entries as a list of groups, so a problem in one is
    located by its position there, which the file does not show. The tag
    naming the kind of a layout node is left out, the file not writing it.
    """
    groups: list[dict[str, Any]] = []
    # grouping fails on an entry that is not a mapping; that entry is then the
    # problem reported, and has no hook points to be named by
    with suppress(ValueError):
        if isinstance(data.get("hooks"), Mapping):
            groups = group_hook_entries(data["hooks"])

    def located(loc: list[str | int]) -> list[str | int]:
        if loc[:1] == ["hooks"] and len(loc) > 1 and isinstance(loc[1], int) and groups:
            loc[1] = "+".join(groups[loc[1]]["moments"])
        # the tag naming a layout node's kind is the model's, not the file's
        return [
            part
            for part in loc
            if not (isinstance(part, str) and part.startswith("node:"))
        ]

    return problem_lines(error, located)


def nonempty_path(value: Any) -> Any:
    """Refuse an empty path, which would mean the working directory."""
    if value == "":
        raise ValueError("an empty path; leave the key out for the default")
    return value


UserPath = Annotated[
    Path, BeforeValidator(nonempty_path), AfterValidator(Path.expanduser)
]
"""A path as a session file writes it, with `~` expanded."""


class CatalogConfig(
    BaseModel, extra="forbid", frozen=True, use_attribute_docstrings=True
):
    """The catalog a session keeps in `<base_dir>/<session>/catalog`."""

    readable: tuple[UserPath, ...] = ()
    """Directories the catalog may read from besides the session's own."""


def with_empty_catalog(section: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a `storage` section whose present but empty `catalog` is a mapping.

    An empty key asks for a catalog with every default, which only the raw
    section can tell apart from an absent one.
    """
    if section.get("catalog", {}) is None:
        return {**section, "catalog": {}}
    return section


class StorageConfig(
    BaseModel, extra="forbid", frozen=True, use_attribute_docstrings=True
):
    """Where a session writes, and whether it keeps a catalog of its runs."""

    base_dir: UserPath | None = None
    """Root the session writes under; `None` is the user data directory."""

    max_digits: int = 5
    """Width of the counter in file names."""

    catalog: CatalogConfig | None = None
    """The session's catalog, needing the `tiled` extra; `None` for none."""


def validate_session(sources: Sequence[Source], data: Mapping[str, Any]) -> SessionFile:
    """Return *data*, the merged content of *sources*, as a session file.

    Raises
    ------
    ConfigurationError
        Listing every problem, and naming *sources*.
    """
    try:
        return SessionFile.model_validate(data)
    except ValidationError as e:
        raise ConfigurationError(
            [label(source) for source in sources], problems_of(e, data)
        ) from None


class ComponentEntry(BaseModel, extra="allow", use_attribute_docstrings=True):
    """A component's entry: the plugin it comes from, and its constructor keywords.

    Every key besides the plugin keys is a keyword for the component's
    constructor, which checks them when the component is built.
    """

    plugin_name: str | None = None
    """The plugin whose manifest lists the component."""

    plugin_id: str | None = None
    """The component's id in that manifest."""

    @model_validator(mode="after")
    def pair_plugin_keys(self) -> ComponentEntry:
        """Refuse a misspelled plugin key, and one plugin key without the other."""
        # the misspelling first: it is why the other key looks missing
        for key in self.model_extra or {}:
            if key.startswith("plugin_"):
                close = get_close_matches(key, PLUGIN_KEYS, n=1)
                hint = f"; did you mean {close[0]!r}?" if close else ""
                raise ValueError(
                    f"{key!r} is not a plugin key, which are {PLUGIN_KEYS}{hint}"
                )
        if (self.plugin_name is None) != (self.plugin_id is None):
            given, missing = (
                ("plugin_name", "plugin_id")
                if self.plugin_id is None
                else ("plugin_id", "plugin_name")
            )
            raise ValueError(
                f"{given} is given without {missing}; give both or neither"
            )
        return self


class DeviceEntry(ComponentEntry):
    """A device's entry, with the keys the container keeps from its constructor."""

    service: str | None = None
    """The service whose prefix the device gets."""

    autoconnect: bool = Field(default=True, strict=True)
    """Whether the build connects the device."""


class ViewEntry(ComponentEntry):
    """A view's entry, with the key the session keeps from its constructor."""

    placement: str | dict[str, str] | None = None
    """Where the view attaches, as a word or mapping the session's frontend reads."""


class RowEntry(BaseModel, extra="forbid", use_attribute_docstrings=True):
    """Views side by side in a layout, as a session file writes them."""

    row: list[NodeEntry]
    """What shares the space, left to right."""

    sizes: list[float] | None = None
    """One positive weight per child."""

    @model_validator(mode="after")
    def fits(self) -> RowEntry:
        """Refuse sizes that do not give one positive weight per child, and an empty row."""
        problems = split_problems(len(self.row), self.sizes)
        if problems:
            raise ValueError("; ".join(problems))
        return self


class ColumnEntry(BaseModel, extra="forbid", use_attribute_docstrings=True):
    """Views stacked in a layout, as a session file writes them."""

    column: list[NodeEntry]
    """What shares the space, top to bottom."""

    sizes: list[float] | None = None
    """One positive weight per child."""

    @model_validator(mode="after")
    def fits(self) -> ColumnEntry:
        """Refuse sizes that do not give one positive weight per child, and an empty column."""
        problems = split_problems(len(self.column), self.sizes)
        if problems:
            raise ValueError("; ".join(problems))
        return self


class TabsEntry(BaseModel, extra="forbid", use_attribute_docstrings=True):
    """Views sharing one space as tabs, as a session file writes them."""

    tabs: list[str]
    """The views, in the order of their tabs."""

    current: str | None = None
    """The view shown on top; the first when left out."""

    @model_validator(mode="after")
    def fits(self) -> TabsEntry:
        """Refuse empty tabs, and a current tab that is not one of them."""
        problems = tabs_problems(self.tabs, self.current)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def node_kind(value: object) -> str:
    """Return the tag of the kind of layout node *value* writes, `node:unknown` for no kind or several."""
    match value:
        case str():
            return "node:name"
        case RowEntry():
            return "node:row"
        case ColumnEntry():
            return "node:column"
        case TabsEntry():
            return "node:tabs"
        case Mapping():
            kinds = [kind for kind in ("row", "column", "tabs") if kind in value]
            return f"node:{kinds[0]}" if len(kinds) == 1 else "node:unknown"
    return "node:unknown"


def unknown_node(value: object) -> object:
    """Refuse a layout node of no kind, or of several."""
    # a ValueError, since pydantic reports no other at the key's location
    raise ValueError(
        "a node is a view's name, or a mapping with one of the keys row, column or tabs"
    )


NodeEntry: TypeAlias = Annotated[
    Annotated[str, Tag("node:name")]
    | Annotated[RowEntry, Tag("node:row")]
    | Annotated[ColumnEntry, Tag("node:column")]
    | Annotated[TabsEntry, Tag("node:tabs")]
    | Annotated[Any, AfterValidator(unknown_node), Tag("node:unknown")],
    Discriminator(node_kind),
]
"""A view's name, or views arranged together, as a session file writes them."""

RowEntry.model_rebuild()
ColumnEntry.model_rebuild()


def node_of(entry: NodeEntry) -> Node:
    """Return the layout node a session file's *entry* writes."""
    match entry:
        case str():
            return entry
        case RowEntry(row=children, sizes=sizes):
            return Row(*map(node_of, children), sizes=sizes)
        case ColumnEntry(column=children, sizes=sizes):
            return Column(*map(node_of, children), sizes=sizes)
        case TabsEntry(tabs=names, current=current):
            return Tabs(*names, current=current)
    # validation refuses any other node before this reads it
    raise TypeError(f"{entry!r} is no layout node")


class LayoutEntry(BaseModel, extra="forbid", use_attribute_docstrings=True):
    """The first layout of the window, as a session file writes it."""

    regions: dict[str, NodeEntry] = {}
    """What fills each region, by the frontend's region names."""

    sizes: dict[str, float] = {}
    """The share of the window each region takes, between 0 and 1."""

    hidden: list[str] = []
    """The views that start hidden."""

    @model_validator(mode="after")
    def fits(self) -> LayoutEntry:
        """Refuse a view placed twice and a share outside (0, 1)."""
        problems = layout_problems(
            {region: node_of(entry) for region, entry in self.regions.items()},
            self.sizes,
        )
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def to_layout(self) -> WindowLayout:
        """Return the layout this entry writes."""
        return WindowLayout(
            {region: node_of(entry) for region, entry in self.regions.items()},
            self.sizes,
            self.hidden,
        )


class SessionFile(BaseModel, extra="forbid", use_attribute_docstrings=True):
    """A session file, after its layers are merged."""

    schema_version: float = Field(1.0, strict=True)
    """The schema the file is written for, one of `SCHEMA_VERSIONS`."""

    frontend: str | None = None
    """The registered frontend the session builds on; the calling class if unset."""

    session: str | None = None
    """The session's name, which also names its application; its class's name if unset."""

    metadata: dict[str, Any] = {}
    """Metadata of the session."""

    strict: bool = False
    """Whether a component that fails to build or set up stops the session."""

    mock: bool = False
    """Whether devices connect to simulated backends and no service is launched."""

    transport: str | None = None
    """What the session's services speak, from the `services` section."""

    services: dict[str, ComponentEntry] = {}
    """Services by name."""

    devices: dict[str, DeviceEntry] = {}
    """Devices by name."""

    presenters: dict[str, ComponentEntry] = {}
    """Presenters by name."""

    views: dict[str, ViewEntry] = {}
    """Views by name."""

    layout: LayoutEntry | None = None
    """The first layout of the window, in place of the one the session class declares."""

    shortcuts: dict[str, str | list[str] | None] = {}
    """Keys by command id, `<component>.<method>`, replacing what the component declares; `null` unbinds."""

    storage: StorageConfig | None = None
    """Where the session writes; the defaults when absent."""

    wiring: dict[str, str | list[str]] = {}
    """The slots each signal reaches, both written as `component.port`."""

    pairs: list[tuple[str, str]] = []
    """Components linked to each other, two names each.

    Each signal of one reaches each slot of the other that names it in its
    `signal`, both ways.
    """

    hooks: list[HookGroup] = []
    """Hook providers, one group per distinct entry."""

    providers: dict[str, ComponentEntry] = {}
    """Classes registering values the session hands to components, by name."""

    actions: Any = None
    """Menu actions the Qt session registers, checked when it reads them."""

    color_scheme: Any = None
    """The Qt session's color scheme, checked when it reads it."""

    @model_validator(mode="wrap")
    @classmethod
    def normalize_sections(
        cls, data: Any, handler: ModelWrapValidatorHandler[SessionFile]
    ) -> SessionFile:
        """Validate the file as the model holds it, reporting every problem at once.

        What preparing the file finds wrong is reported beside what the fields
        find wrong, rather than instead of it.
        """
        if not isinstance(data, Mapping):
            return handler(data)
        data, problems = prepared(data)
        try:
            session = handler(data)
        except ValidationError as e:
            problems.extend(cast("list[InitErrorDetails]", e.errors()))
            raise ValidationError.from_exception_data(cls.__name__, problems) from None
        if problems:
            raise ValidationError.from_exception_data(cls.__name__, problems)
        return session

    @field_validator("transport")
    @classmethod
    def known_transport(cls, value: str | None) -> str | None:
        """Refuse a transport redsun does not have."""
        if value is not None and value not in TRANSPORTS:
            known = ", ".join(repr(key) for key in sorted(TRANSPORTS))
            # a ValueError, since pydantic reports no other at the key's location
            raise ValueError(f"asks for transport {value!r}; redsun has {known}")
        return value

    @field_validator("frontend")
    @classmethod
    def registered_frontend(cls, value: str | None) -> str | None:
        """Refuse a frontend no installed package registers."""
        if value is None:
            return None
        known = frontends()
        if value not in known:
            listed = ", ".join(repr(name) for name in sorted(known)) or "none"
            # a ValueError, since pydantic reports no other at the key's location
            raise ValueError(f"asks for frontend {value!r}; registered: {listed}")
        return value

    @field_validator("shortcuts")
    @classmethod
    def two_keys_at_most(
        cls, value: dict[str, str | list[str] | None]
    ) -> dict[str, str | list[str] | None]:
        """Refuse a command given more than two keys."""
        for command, keys in value.items():
            if isinstance(keys, list) and len(keys) > 2:
                # a ValueError, since pydantic reports no other at the key's location
                raise ValueError(
                    f"gives {command!r} {len(keys)} keys; a command takes two at most"
                )
        return value

    @field_validator("pairs")
    @classmethod
    def two_components(cls, value: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Refuse a pairing that names one component twice."""
        for first, second in value:
            if first == second:
                # a ValueError, since pydantic reports no other at the key's location
                raise ValueError(f"pairs {first!r} with itself; a pairing names two")
        return value

    @field_validator("schema_version")
    @classmethod
    def supported_schema_version(cls, value: float) -> float:
        """Refuse a schema version this redsun does not read."""
        if value not in SCHEMA_VERSIONS:
            known = ", ".join(str(version) for version in SCHEMA_VERSIONS)
            raise ValueError(
                f"schema_version {value} is not one this redsun reads ({known}); "
                f"upgrade redsun or write the file for {SCHEMA_VERSIONS[-1]}"
            )
        return value


def session_file_schema() -> dict[str, Any]:
    """Return the JSON schema of a session file as written, not as `SessionFile` holds it.

    The model lifts `services.transport` out of the `services` section and
    groups hook entries into a list; a file keeps both where it wrote them,
    and may leave a section empty.
    """
    schema = SessionFile.model_json_schema(by_alias=True)
    properties = schema["properties"]
    del properties["transport"]
    properties["schema_version"]["enum"] = list(SCHEMA_VERSIONS)
    properties["frontend"]["anyOf"][0]["enum"] = sorted(frontends())
    properties["services"] = {
        "type": "object",
        "properties": {TRANSPORT_KEY: {"enum": sorted(TRANSPORTS)}},
        "additionalProperties": {"$ref": "#/$defs/ComponentEntry"},
    }
    groups = schema["$defs"].pop("HookGroup")
    del groups["properties"]["moments"]
    groups["required"].remove("moments")
    groups["title"] = "HookEntry"
    schema["$defs"]["HookEntry"] = groups
    properties["hooks"] = {
        "type": "object",
        "additionalProperties": {
            "anyOf": [{"type": "string"}, {"$ref": "#/$defs/HookEntry"}]
        },
    }
    for section in (*EMPTY_AS_MAPPING, "hooks", "pairs"):
        properties[section] = {"anyOf": [properties[section], {"type": "null"}]}
    return schema


def refusal(loc: tuple[str, ...], message: str) -> InitErrorDetails:
    """Return a problem found while preparing a file, at *loc*."""
    return {
        "type": PydanticCustomError("session_file", message),
        "loc": loc,
        "input": None,
    }


def prepared(data: Mapping[str, Any]) -> tuple[dict[str, Any], list[InitErrorDetails]]:
    """Return a session file shaped as `SessionFile` holds it, and what stops that.

    Empty sections are read as empty, `services.transport` is lifted beside
    the sections, and hook entries are grouped. A problem found on the way is
    returned rather than raised, and the part it concerns left out, so the
    rest of the file is still validated.
    """
    data = {
        key: {} if value is None and key in EMPTY_AS_MAPPING else value
        for key, value in data.items()
    }
    if "pairs" in data and data["pairs"] is None:
        data["pairs"] = []
    problems: list[InitErrorDetails] = []
    if TRANSPORT_KEY in data:
        del data[TRANSPORT_KEY]
        problems.append(
            refusal(
                (TRANSPORT_KEY,),
                f"{TRANSPORT_KEY!r} goes under 'services', where every service "
                "of the session reads it",
            )
        )
    services = data.get("services")
    if isinstance(services, Mapping) and TRANSPORT_KEY in services:
        services = dict(services)
        data["transport"] = services.pop(TRANSPORT_KEY)
        data["services"] = services
    if isinstance(data.get("storage"), Mapping):
        data["storage"] = with_empty_catalog(data["storage"])
    hooks = data.get("hooks")
    if hooks is None:
        data["hooks"] = []
    elif not isinstance(hooks, Mapping):
        data["hooks"] = []
        problems.append(
            refusal(("hooks",), "'hooks' must be a mapping of hook points to entries")
        )
    else:
        # before anything is copied: entries a YAML anchor shares are known
        # only by being one object
        try:
            data["hooks"] = group_hook_entries(hooks)
        except ValueError as e:
            data["hooks"] = []
            problems.append(refusal(("hooks",), str(e)))
    return data, problems
