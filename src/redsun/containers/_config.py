from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NotRequired

from redsun.virtual import RedSunConfig

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
