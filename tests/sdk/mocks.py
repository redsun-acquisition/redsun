"""Mock classes for redsun SDK tests."""

from __future__ import annotations

from typing import Any

from ophyd_async.core import SignalRW, StandardReadable, soft_signal_rw


class MockDetector(StandardReadable):
    """Mock detector device using soft signals.

    The EGU for ``exposure`` is embedded in the descriptor document
    (``describe()["<name>-exposure"]["units"]``), not as a separate signal.
    """

    exposure: SignalRW[float]
    integer: SignalRW[int]
    floating: SignalRW[float]

    def __init__(
        self,
        name: str,
        *,
        exposure: float = 1.0,
        exposure_units: str = "ms",
        integer: int = 0,
        floating: float = 0.0,
        **_: Any,
    ) -> None:
        with self.add_children_as_readables():
            self.exposure = soft_signal_rw(
                float, initial_value=exposure, units=exposure_units
            )
            self.integer = soft_signal_rw(int, initial_value=integer)
            self.floating = soft_signal_rw(float, initial_value=floating)
        super().__init__(name=name)
