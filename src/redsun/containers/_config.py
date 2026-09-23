from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from contextlib import suppress
from difflib import get_close_matches
from enum import Enum, unique
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Final, NotRequired, cast

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Field,
    ModelWrapValidatorHandler,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from redsun.virtual import RedSunConfig

from ..services._transports import TRANSPORTS
from ._hooks import HookGroup, group_hook_entries
from ._manifest import problem_lines

if TYPE_CHECKING:
    from pydantic_core import InitErrorDetails

    from redsun.containers.components import _ComponentField as ComponentField

logger = logging.getLogger("redsun")

TRANSPORT_KEY: Final = "transport"
"""The key of the ``services`` section naming what its services speak."""

COMPONENT_SECTIONS: frozenset[str] = frozenset(
    {"services", "devices", "presenters", "views"}
)
"""The configuration sections whose entries are a component's constructor call."""

IDENTITY_KEYS: tuple[str, ...] = ("schema_version", "frontend")
"""Keys saying what kind of session this is, on which layered files must agree.

Every other key describes the session's content, which a later file may
override.
"""

SCHEMA_VERSIONS: Final = (1.0,)
"""The session file schema versions this redsun reads."""

PLUGIN_KEYS: Final = ("plugin_name", "plugin_id")
"""The keys naming the plugin a component comes from."""

EMPTY_AS_MAPPING: Final = frozenset(
    {"metadata", "services", "devices", "presenters", "views"}
)
"""Sections a file may write empty, read as an empty mapping."""

__all__ = ["AppConfig", "ConfigurationError", "Frontend"]


class ConfigurationError(ValueError):
    """A session file, once its layers are merged, says what a session cannot."""

    def __init__(self, paths: Sequence[Path], problems: Sequence[str]) -> None:
        named = ", ".join(str(path) for path in paths)
        lines = "\n".join(f"  {problem}" for problem in problems)
        super().__init__(f"Configuration ({named}) is invalid:\n{lines}")


def problems_of(error: ValidationError, data: Mapping[str, Any]) -> list[str]:
    """Say each problem as ``section.key: what``, a hook entry by its hook points.

    The model holds hook entries as a list of groups, so a problem in one is
    located by its position there, which the file does not show.
    """
    groups: list[dict[str, Any]] = []
    # grouping fails on an entry that is not a mapping; that entry is then the
    # problem reported, and has no hook points to be named by
    with suppress(ValueError):
        if isinstance(data.get("hooks"), Mapping):
            groups = group_hook_entries(data["hooks"])

    def by_hook_points(loc: list[str | int]) -> list[str | int]:
        if loc[:1] == ["hooks"] and len(loc) > 1 and isinstance(loc[1], int) and groups:
            loc[1] = "+".join(groups[loc[1]]["moments"])
        return loc

    return problem_lines(error, by_hook_points)


@unique
class Frontend(str, Enum):
    """Supported frontend types."""

    PYQT = "pyqt"
    PYSIDE = "pyside"


def nonempty_path(value: Any) -> Any:
    """Refuse an empty path, which would mean the working directory."""
    if value == "":
        raise ValueError("an empty path; leave the key out for the default")
    return value


UserPath = Annotated[
    Path, BeforeValidator(nonempty_path), AfterValidator(Path.expanduser)
]
"""A path as a session file writes it, with ``~`` expanded."""


class CatalogConfig(
    BaseModel, extra="forbid", frozen=True, use_attribute_docstrings=True
):
    """The catalog a session keeps in `<base_dir>/<session>/catalog`."""

    readable: tuple[UserPath, ...] = ()
    """Directories the catalog may read from besides the session's own."""


def with_empty_catalog(section: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a ``storage`` section whose present but empty ``catalog`` is a mapping.

    An empty key asks for a catalog with every default, which only the raw
    section can tell apart from an absent one.
    """
    if section.get("catalog", {}) is None:
        return {**section, "catalog": {}}
    return section


def storage_of(section: Mapping[str, Any] | None) -> StorageConfig:
    """Read a ``storage`` section, the defaults when it is absent or empty."""
    return StorageConfig.model_validate(with_empty_catalog(section or {}))


class StorageConfig(
    BaseModel, extra="forbid", frozen=True, use_attribute_docstrings=True
):
    """Where a session writes, and whether it keeps a catalog of its runs."""

    base_dir: UserPath | None = None
    """Root the session writes under; `None` is the user data directory."""

    max_digits: int = 5
    """Width of the counter in file names."""

    catalog: CatalogConfig | None = None
    """The session's catalog, needing the ``tiled`` extra; `None` for none."""


class AppConfig(RedSunConfig, total=False):
    """Configuration of an application container.

    [`RedSunConfig`][redsun.virtual.RedSunConfig] plus the component sections,
    which the container reads and does not pass to components.
    """

    services: NotRequired[dict[str, Any]]
    devices: NotRequired[dict[str, Any]]
    presenters: NotRequired[dict[str, Any]]
    views: NotRequired[dict[str, Any]]
    storage: NotRequired[dict[str, Any] | None]
    wiring: NotRequired[list[dict[str, str]]]
    hooks: NotRequired[dict[str, dict[str, Any]]]


def read_yaml(path: Path) -> dict[str, Any]:
    """Read one YAML file into a mapping, unvalidated."""
    with open(path) as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise TypeError(
            f"Expected a YAML mapping at top level in {path}, got {type(data).__name__}"
        )
    return data


def merge_config(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Return *base* with *overlay* laid over it, merging nested mappings.

    A key in both is taken from *overlay* unless both values are mappings,
    which merge in turn. Lists and scalars are replaced, not combined.

    Component entries are the exception: ``services``, ``devices``,
    ``presenters`` and ``views`` merge by component name, but a component
    *named* in *overlay* is taken from it whole. Its entry is a constructor
    call's keyword arguments, so one file owns them all and a reader stops at
    the last file naming it.
    """
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if not (isinstance(current, dict) and isinstance(value, dict)):
            merged[key] = value
        elif key in COMPONENT_SECTIONS:
            for shadowed in current.keys() & value.keys():
                logger.debug(
                    f"Component '{shadowed}' in '{key}' is taken from a later "
                    f"configuration file, replacing the entry under it"
                )
            merged[key] = {**current, **value}
        else:
            merged[key] = merge_config(current, value)
    return merged


def refuse_identity_conflict(
    data: dict[str, Any], overlay: dict[str, Any], path: Path
) -> None:
    """Refuse a file contradicting what kind of session an earlier one declared.

    Raises
    ------
    ValueError
        If *overlay* changes a key naming the session's kind.
    """
    for key in IDENTITY_KEYS:
        if key in data and key in overlay and data[key] != overlay[key]:
            raise ValueError(
                f"Configuration file {path} sets {key}={overlay[key]!r}, "
                f"which contradicts {data[key]!r} from a file layered under it. "
                f"{key} names what kind of session this is, so every file must "
                f"agree on it."
            )


def transport_of(data: dict[str, Any]) -> str | None:
    """Return the transport a configuration names, or ``None`` for none."""
    services = data.get("services") or {}
    return services.get(TRANSPORT_KEY) if isinstance(services, dict) else None


def checked_transport(name: str, where: str) -> str:
    """Return *name*, refusing a transport ``redsun`` does not have.

    Raises
    ------
    TypeError
        Naming what was read and the transports there are.
    """
    if name not in TRANSPORTS:
        known = ", ".join(repr(key) for key in sorted(TRANSPORTS))
        raise TypeError(f"{where} asks for transport {name!r}; redsun has {known}")
    return name


def load_yaml(paths: Sequence[Path]) -> dict[str, Any]:
    """Read *paths* in order, merge each over the previous, and validate the result.

    The merged mapping is validated as a whole, not per file, so a layered file
    may hold a fragment. It is returned as read: entries a YAML anchor shares
    stay one object.

    Raises
    ------
    ValueError
        If two files disagree about the session's schema version or frontend.
    ConfigurationError
        Listing every problem of the merged mapping.
    """
    data = merge_files(paths)
    validate_session(paths, data)
    return data


def merge_files(paths: Sequence[Path]) -> dict[str, Any]:
    """Read *paths* in order and merge each over the previous, unvalidated.

    Raises
    ------
    ValueError
        If two files disagree about the session's schema version, frontend or
        transport.
    """
    if len(paths) > 1:
        logger.debug(f"Reading configuration from {len(paths)} files, in order:")
        for position, path in enumerate(paths, 1):
            logger.debug(f"  {position}. {path}")
    data: dict[str, Any] = {}
    transport: tuple[str, Path] | None = None
    for path in paths:
        overlay = read_yaml(path)
        refuse_identity_conflict(data, overlay, path)
        named = transport_of(overlay)
        if named is not None and transport is not None and named != transport[0]:
            raise ValueError(
                f"Configuration file {path} sets {TRANSPORT_KEY}={named!r} under "
                f"services, which contradicts {transport[0]!r} from {transport[1]}. "
                "Every service of a session speaks the same transport, so every "
                "file must agree on it."
            )
        if named is not None and transport is None:
            transport = (named, path)
        data = merge_config(data, overlay)
    return data


def validate_session(paths: Sequence[Path], data: Mapping[str, Any]) -> None:
    """Validate *data*, the merged content of *paths*, as a session file.

    Raises
    ------
    ConfigurationError
        Listing every problem, and naming *paths*.
    """
    try:
        SessionFile.model_validate(data)
    except ValidationError as e:
        raise ConfigurationError(paths, problems_of(e, data)) from None


def refuse_unresolved_fields(
    owner: str, paths: Sequence[Path], fields: Mapping[str, ComponentField]
) -> None:
    """Refuse the container *owner* when a ``from_config`` field has no file.

    Checked at construction, not class creation, since a base class leaves
    ``config`` to its subclasses.

    Raises
    ------
    TypeError
        Naming every field wanting a configuration section.
    """
    if paths:
        return
    unresolved = sorted(
        attr_name
        for attr_name, field in fields.items()
        if field.from_config is not None
    )
    if unresolved:
        raise TypeError(
            f"Component field(s) {', '.join(unresolved)} in {owner} have "
            f"from_config set but no config path was provided to the container "
            f"class"
        )


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


class WiringRule(BaseModel, extra="forbid", use_attribute_docstrings=True):
    """One connection a session file declares, from a signal to a slot."""

    from_: str = Field(alias="from")
    """The signal, as ``component.signal``."""

    to: str
    """The slot, as ``component.slot``."""


class SessionFile(BaseModel, extra="forbid", use_attribute_docstrings=True):
    """A session file, after its layers are merged."""

    schema_version: float = Field(strict=True)
    """The schema the file is written for, one of `SCHEMA_VERSIONS`."""

    frontend: Frontend
    """The toolkit the session runs on."""

    session: str = "Redsun"
    """The session's display name."""

    metadata: dict[str, Any] = {}
    """Metadata of the session."""

    transport: str | None = None
    """What the session's services speak, from the ``services`` section."""

    services: dict[str, ComponentEntry] = {}
    """Services by name."""

    devices: dict[str, DeviceEntry] = {}
    """Devices by name."""

    presenters: dict[str, ComponentEntry] = {}
    """Presenters by name."""

    views: dict[str, ComponentEntry] = {}
    """Views by name."""

    storage: StorageConfig | None = None
    """Where the session writes; the defaults when absent."""

    wiring: list[WiringRule] = []
    """Connections the session declares."""

    hooks: list[HookGroup] = []
    """Hook providers, one group per distinct entry."""

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

    @field_validator("frontend", mode="before")
    @classmethod
    def known_frontend(cls, value: Any) -> Any:
        """Refuse a frontend no container runs on."""
        known = [frontend.value for frontend in Frontend]
        if value not in known:
            raise ValueError(f"Unknown frontend {value!r}. Supported: {known}")
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

    The model lifts ``services.transport`` out of the ``services`` section and
    groups hook entries into a list; a file keeps both where it wrote them,
    and may leave a section empty.
    """
    schema = SessionFile.model_json_schema(by_alias=True)
    properties = schema["properties"]
    del properties["transport"]
    properties["schema_version"]["enum"] = list(SCHEMA_VERSIONS)
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
        "additionalProperties": {"$ref": "#/$defs/HookEntry"},
    }
    for section in (*EMPTY_AS_MAPPING, "hooks", "wiring"):
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

    Empty sections are read as empty, ``services.transport`` is lifted beside
    the sections, and hook entries are grouped. A problem found on the way is
    returned rather than raised, and the part it concerns left out, so the
    rest of the file is still validated.

    Hook entries are grouped here, before anything is copied, since the
    entries a YAML anchor shares are known only by being one object.
    """
    data = {
        key: {} if value is None and key in EMPTY_AS_MAPPING else value
        for key, value in data.items()
    }
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
    if "wiring" in data and data["wiring"] is None:
        data["wiring"] = []
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
        try:
            data["hooks"] = group_hook_entries(hooks)
        except ValueError as e:
            data["hooks"] = []
            problems.append(refusal(("hooks",), str(e)))
    return data, problems
