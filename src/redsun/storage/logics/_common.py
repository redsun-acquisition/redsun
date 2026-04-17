from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ophyd_async.core import SignalRW


@dataclass
class NDArrayInfo:
    """Information about the source frames for a given data key."""

    x: SignalRW[int]
    """The x offset of the region of interest."""

    y: SignalRW[int]
    """The y offset of the region of interest."""

    height: SignalRW[int]
    """The height of the region of interest."""

    width: SignalRW[int]
    """The width of the region of interest."""

    numpy_dtype: SignalRW[str]
    """NumPy data type as a string for the source frames."""
