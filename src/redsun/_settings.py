"""Preferences a session keeps between runs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from platformdirs import user_config_dir

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import TypeAlias

    JsonValue: TypeAlias = (
        str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
    )
    """A value the settings file can hold."""

__all__ = ["Settings"]

logger = logging.getLogger("redsun")


class Settings:
    """What a session remembers about how one user likes to run it.

    Kept per user and per machine, apart from the session file.

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
        self._values: dict[str, JsonValue] = read(path)

    @classmethod
    def for_session(cls, name: str) -> Self:
        """Return the settings of the session called *name*.

        Sessions do not share a file.
        """
        # a layout saved by one session means nothing to another
        return cls(Path(user_config_dir("redsun", appauthor=False)) / f"{name}.json")

    @property
    def path(self) -> Path:
        """Where the settings are read from and written to."""
        return self._path

    def get(self, key: str, default: Any = None) -> Any:
        """Return what *key* was last set to, or *default*."""
        return self._values.get(key, default)

    def set(self, key: str, value: JsonValue) -> None:
        """Remember *value* under *key*, and write the file.

        Written as it is set rather than at shutdown.

        Raises
        ------
        TypeError
            If *value* is not JSON-serializable.
        """
        values = {**self._values, key: value}
        # serialized before it is kept, so a value refused leaves nothing behind
        text = json.dumps(values, indent=2)
        self._values = values
        # now, so a session that crashes later keeps what the user chose
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(text, encoding="utf-8")

    def __contains__(self, key: str) -> bool:
        """Whether *key* has been set."""
        return key in self._values

    def __iter__(self) -> Iterator[str]:
        """Iterate the keys that have been set."""
        return iter(self._values)

    def __repr__(self) -> str:
        return f"Settings({str(self._path)!r}, {len(self._values)} keys)"


def read(path: Path) -> dict[str, JsonValue]:
    """Return what *path* holds, or nothing when it is absent or unreadable.

    A file that cannot be parsed is logged as a warning and read as empty,
    so the session comes up with defaults.
    """
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    # only the program writes this file, so a broken one is damage rather
    # than a mistake to stop the user for
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Ignoring unreadable settings at %s: %s", path, e)
        return {}
    if not isinstance(loaded, dict):
        logger.warning("Ignoring settings at %s: expected an object", path)
        return {}
    return loaded
