from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NotRequired

from redsun.virtual import RedSunConfig

__all__ = ["AppConfig", "TiledConfig"]


@dataclass(frozen=True, slots=True)
class TiledConfig:
    """Where a session's catalog lives, and what it may register.

    Parameters
    ----------
    directory : Path | None
        Directory of the catalog. `None`, the default, is the session's own
        `<base_dir>/<session>/catalog`, which is resolved when the catalog is
        built, since the session name is not known while the file is read.
    readable : tuple[Path, ...]
        Further directories the catalog may register assets from. The session's
        own directory is always readable; these are added to it, for services
        writing where their own configuration says.
    """

    directory: Path | None = None
    readable: tuple[Path, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any] | None) -> TiledConfig:
        """Read a session file's `tiled` section. Present and empty is valid.

        Raises
        ------
        TypeError
            If the section is not a mapping.
        ValueError
            If the section names a key it has no place for.
        """
        if section is None:
            return cls()
        if not isinstance(section, Mapping):
            raise TypeError(
                f"the 'tiled' section must be a mapping, got {type(section).__name__}"
            )
        unknown = sorted(set(section) - {"directory", "readable"})
        if unknown:
            named = ", ".join(repr(key) for key in unknown)
            raise ValueError(
                f"the 'tiled' section names {named}, which it has no key for; "
                "it takes 'directory' and 'readable'"
            )
        directory = section.get("directory")
        return cls(
            directory=Path(directory).expanduser() if directory else None,
            readable=tuple(
                Path(path).expanduser() for path in section.get("readable") or ()
            ),
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
    storage: NotRequired[dict[str, Any]]
    tiled: NotRequired[dict[str, Any] | None]
    wiring: NotRequired[list[dict[str, str]]]
    hooks: NotRequired[dict[str, dict[str, Any]]]
