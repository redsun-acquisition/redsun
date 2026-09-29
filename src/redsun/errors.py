"""The exceptions a session raises."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

__all__ = [
    "BuildError",
    "ConfigurationError",
    "ConfigurationInUse",
    "HookError",
    "PluginError",
]


class BuildError(RuntimeError):
    """Raised when a strict session could not build or set up a component."""


class ConfigurationError(ValueError):
    """Raised when a session file, once its layers are merged, says what a session cannot.

    Parameters
    ----------
    sources
        The sources the configuration was read from, as the message names
        them: a file path, or `an inline mapping`.
    problems
        One line for each problem, as `section.key: what`.
    """

    def __init__(self, sources: Sequence[str], problems: Sequence[str]) -> None:
        lines = "\n".join(f"  {problem}" for problem in problems)
        super().__init__(f"Configuration ({', '.join(sources)}) is invalid:\n{lines}")


class ConfigurationInUse(OSError):
    """Raised when a session is asked to write over a source it was built from."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"{path} is a source this session was built from")
        self.path = path
        """The source the session was asked to write over."""


class HookError(RuntimeError):
    """Raised when a `hooks` configuration entry cannot be turned into a provider."""


class PluginError(RuntimeError):
    """Raised when a configuration entry names a plugin, group or id that does not resolve."""
