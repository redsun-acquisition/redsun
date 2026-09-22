from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NotRequired

import yaml

from redsun.virtual import RedSunConfig

from ..services._transports import TRANSPORTS

if TYPE_CHECKING:
    from redsun.containers.components import _ComponentField as ComponentField

logger = logging.getLogger("redsun")

__all__ = ["AppConfig", "CatalogConfig", "StorageConfig"]


@dataclass(frozen=True, slots=True)
class CatalogConfig:
    """The catalog a session keeps in `<base_dir>/<session>/catalog`.

    Parameters
    ----------
    readable : tuple[Path, ...]
        Directories the catalog may read from besides the session's own.
    """

    readable: tuple[Path, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class StorageConfig:
    """Where a session writes, and whether it keeps a catalog of its runs.

    Parameters
    ----------
    base_dir : Path | None
        Root the session writes under. `None` is the user data directory.
    max_digits : int
        Width of the counter in file names.
    catalog : CatalogConfig | None
        The session's catalog, needing the ``tiled`` extra; `None` for none.
    """

    base_dir: Path | None = None
    max_digits: int = 5
    catalog: CatalogConfig | None = None

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any] | None) -> StorageConfig:
        """Read a session file's `storage` section. An empty `catalog` key is a catalog.

        Raises
        ------
        TypeError
            If the section, or its `catalog` key, is not a mapping, or
            `readable` is not a list.
        ValueError
            If either names a key it has no place for.
        """
        section = mapping_of(section, "storage")
        refuse_unknown(section, "storage", ("base_dir", "max_digits", "catalog"))
        catalog = None
        if "catalog" in section:
            entry = mapping_of(section["catalog"], "storage.catalog")
            refuse_unknown(entry, "storage.catalog", ("readable",))
            readable = entry.get("readable") or []
            if not isinstance(readable, list):
                raise TypeError(
                    "'storage.catalog.readable' must be a list of directories, "
                    f"got {type(readable).__name__}"
                )
            catalog = CatalogConfig(
                readable=tuple(Path(path).expanduser() for path in readable)
            )
        base_dir = section.get("base_dir")
        return cls(
            base_dir=Path(base_dir).expanduser() if base_dir else None,
            max_digits=section.get("max_digits", 5),
            catalog=catalog,
        )


def mapping_of(section: Any, name: str) -> Mapping[str, Any]:
    """Return *section*, an empty mapping for `None`, refusing anything else."""
    if section is None:
        return {}
    if not isinstance(section, Mapping):
        raise TypeError(
            f"the {name!r} section must be a mapping, got {type(section).__name__}"
        )
    return section


def refuse_unknown(
    section: Mapping[str, Any], name: str, keys: tuple[str, ...]
) -> None:
    """Raise `ValueError` if *section* names a key outside *keys*."""
    unknown = sorted(set(section) - set(keys))
    if unknown:
        named = ", ".join(repr(key) for key in unknown)
        accepted = ", ".join(repr(key) for key in keys)
        raise ValueError(
            f"the {name!r} section names {named}, which it has no key for; "
            f"it takes {accepted}"
        )


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


COMPONENT_SECTIONS: frozenset[str] = frozenset(
    {"services", "devices", "presenters", "views"}
)
"""The configuration sections whose entries are a component's constructor call."""

TRANSPORT_KEY: Final = "transport"
"""The key of the ``services`` section naming what its services speak."""

IDENTITY_KEYS: tuple[str, ...] = ("schema_version", "frontend")
"""Keys saying what kind of session this is, on which layered files must agree.

Every other key describes the session's content, which a later file may
override.
"""


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

    Required keys are checked on the merged mapping, not per file, so a layered
    file may hold a fragment.

    Raises
    ------
    ValueError
        If two files disagree about the session's schema version or frontend.
    KeyError
        If the merged mapping is missing a key `AppConfig` requires.
    """
    if len(paths) > 1:
        logger.debug(f"Reading configuration from {len(paths)} files, in order:")
        for position, path in enumerate(paths, 1):
            logger.debug(f"  {position}. {path}")
    data: dict[str, Any] = {}
    for path in paths:
        overlay = read_yaml(path)
        refuse_identity_conflict(data, overlay, path)
        data = merge_config(data, overlay)
    missing = AppConfig.__required_keys__ - data.keys()
    if missing:
        named = ", ".join(str(path) for path in paths)
        raise KeyError(
            f"Configuration ({named}) is missing required keys: "
            f"{', '.join(sorted(missing))}"
        )
    return data


def declared_transport(paths: Sequence[Path], default: str) -> str:
    """Return the transport *paths* name, or *default* when none does.

    Raises
    ------
    ValueError
        If two of its files name a different one. Every service of a session
        speaks the same transport, so a file layered over another cannot
        change what a file under it named.
    """
    named: dict[str, Path] = {}
    for path in paths:
        # a file that cannot be read is reported where the rest of it is read
        with suppress(Exception):
            transport = transport_of(read_yaml(path))
            if transport is not None:
                named.setdefault(transport, path)
    if len(named) > 1:
        (first, under), (second, over) = list(named.items())[:2]
        raise ValueError(
            f"Configuration file {over} sets {TRANSPORT_KEY}={second!r} under "
            f"services, which contradicts {first!r} from {under}. Every service "
            f"of a session speaks the same transport, so every file must agree "
            f"on it."
        )
    return next(iter(named), default)


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
