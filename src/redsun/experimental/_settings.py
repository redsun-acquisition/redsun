"""Preferences a session keeps between runs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from platformdirs import user_config_dir

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["Settings"]

logger = logging.getLogger("redsun")


class Settings:
    """What a session remembers about how one user likes to run it.

    Per user and per machine, which is why it is not the session file: two
    microscopes may share a configuration, and neither should inherit the
    other's window layout or the answer someone gave a prompt once.

    A session builds one for itself and registers it, so an action asks for it
    by type. Reading a session that has never written one gives the defaults
    asked for; the file appears the first time something is set.

    ```python
    settings.set("ask_on_close", False)
    settings.get("ask_on_close", True)
    ```
    """

    __slots__ = ("_path", "_values")

    def __init__(self, path: Path) -> None:
        """Read *path* if it is there, and remember where to write it back."""
        self._path = path
        self._values: dict[str, Any] = read(path)

    @classmethod
    def for_session(cls, name: str) -> Self:
        """Return the settings of the session called *name*.

        Sessions do not share a file: a name is what tells one user's two
        sessions apart, and a layout saved by one means nothing to the other.
        """
        return cls(Path(user_config_dir("redsun", appauthor=False)) / f"{name}.json")

    @property
    def path(self) -> Path:
        """Where the settings are read from and written to."""
        return self._path

    def get(self, key: str, default: Any = None) -> Any:
        """Return what *key* was last set to, or *default*."""
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Remember *value* under *key*, and write the file.

        Written as it is set rather than at shutdown, so a session that ends
        badly still remembers what the user chose before it did.

        Raises
        ------
        TypeError
            If *value* is not JSON-serializable.
        """
        self._values[key] = value
        self._write()

    def __contains__(self, key: str) -> bool:
        """Whether *key* has been set."""
        return key in self._values

    def __iter__(self) -> Iterator[str]:
        """Iterate the keys that have been set."""
        return iter(self._values)

    def __repr__(self) -> str:
        return f"Settings({str(self._path)!r}, {len(self._values)} keys)"

    def _write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._values, indent=2), encoding="utf-8")


def read(path: Path) -> dict[str, Any]:
    """Return what *path* holds, or nothing when it is absent or unreadable.

    A settings file is written by the program and read by it, so one that
    cannot be parsed is damage rather than a mistake a user should be stopped
    for. It is reported and the session comes up with defaults.
    """
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Ignoring unreadable settings at %s: %s", path, e)
        return {}
    if not isinstance(loaded, dict):
        logger.warning("Ignoring settings at %s: expected an object", path)
        return {}
    return loaded
