"""Helpers the SDK tests share."""

from __future__ import annotations

import gc
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    import pytest


def messages(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    """Return the text of the records logged at exactly *level*."""
    return [r.getMessage() for r in caplog.records if r.levelno == level]


@contextmanager
def automatic_collection(enabled: bool) -> Generator[None, None, None]:
    """Turn automatic garbage collection on or off, restoring what was found."""
    found = gc.isenabled()
    (gc.enable if enabled else gc.disable)()
    try:
        yield
    finally:
        (gc.enable if found else gc.disable)()


def kept_under(folder: Path) -> str:
    """Return the lines that keep a session's logs, settings and data under *folder*.

    For the start of a script a test runs in a child process: the fixtures of
    `redsun.testing` patch these in the test's own process only.
    """
    lines = (
        "import redsun._settings, redsun.log, redsun.path_provider",
        f"_folder = lambda *a, **k: {str(folder)!r}",
        "redsun._settings.user_config_dir = _folder",
        "redsun.log.user_data_dir = _folder",
        "redsun.path_provider.user_data_dir = _folder",
        "",
    )
    return "\n".join(lines)
