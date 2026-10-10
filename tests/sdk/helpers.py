"""Helpers the SDK tests share."""

from __future__ import annotations

import gc
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

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
