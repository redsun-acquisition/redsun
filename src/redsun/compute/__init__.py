"""Background computation: pools that run calls off the main thread."""

from __future__ import annotations

from ._future import BrokenPool, Future

__all__ = ["BrokenPool", "Future"]
