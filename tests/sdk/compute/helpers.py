"""Functions the compute tests submit to a pool."""

from __future__ import annotations

import threading
from typing import TypeVar

T = TypeVar("T")


def explode() -> None:
    """Raise, as a call or an initializer that cannot run."""
    raise RuntimeError("boom")


def wait_then_return(
    gate: threading.Event, value: T, started: threading.Event | None = None
) -> T:
    """Set *started* if given, wait for *gate*, then return *value*."""
    if started is not None:
        started.set()
    gate.wait(5)
    return value
