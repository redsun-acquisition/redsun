from __future__ import annotations

from dataclasses import dataclass

from psygnal import Signal

from redsun.experimental import BlueskyCallbackRegistry, Placement, slot

from .keys import Absent, Readings


@dataclass(frozen=True)
class Somewhere(Placement):
    """Stand-in placement: the core ships none, and no frontend is named here."""


class MockMotorView:
    """View consuming a shared value, a framework object and an absent one."""

    sig_requested = Signal(str, float)
    placement: Placement = Somewhere()

    def __init__(
        self,
        name: str,
        /,
        callbacks: BlueskyCallbackRegistry,
        readings: Readings,
        missing: Absent | None = None,
        title: str = "",
    ) -> None:
        self.name = name
        self.callbacks = callbacks
        self.readings = readings
        self.missing = missing
        self.title = title

    @slot
    def refresh(self, axis: str, amount: float) -> None:
        self.refreshed = (axis, amount)
