"""The `compute` section of a session, as a session class writes it."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from ._cores import Preset


class ComputeSettings(TypedDict, total=False):
    """The `compute` section a session class declares, key by key."""

    preset: Preset
    """How the compute cores are split between threads and native libraries."""

    cores: int
    """Cap on the compute cores; default: the physical cores less `reserve`."""

    reserve: list[int]
    """Cores kept for the window's thread; default: one physical core."""

    switch_interval_ms: float | None
    """Interpreter thread switch interval in milliseconds; `None` leaves it alone."""
