"""A function in a module that loads Qt, as a worker process should not receive."""

from __future__ import annotations

import qtpy  # noqa: F401


def answer() -> int:
    """Return 42."""
    return 42
