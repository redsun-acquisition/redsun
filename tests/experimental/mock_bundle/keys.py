"""The shared vocabulary of the bundle."""

from __future__ import annotations

from typing import NewType

Readings = NewType("Readings", "dict[str, float]")
"""Current position of every axis, by axis name."""

Calibration = NewType("Calibration", float)
"""A value the bundle's own provider supplies, not any component."""

Absent = NewType("Absent", str)
"""Nothing provides this; a parameter asking for it optionally gets None."""
