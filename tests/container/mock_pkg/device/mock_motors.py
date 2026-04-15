from __future__ import annotations

from typing import Any

from ophyd_async.core import StandardReadable, soft_signal_rw


class MyMotor(StandardReadable):
    """Mock motor device using ophyd-async ``StandardReadable``."""

    def __init__(
        self,
        name: str,
        /,
        *,
        egu: str = "mm",
        integer: int = 0,
        floating: float = 0.0,
        string: str = "",
        **_: Any,
    ) -> None:
        with self.add_children_as_readables():
            self.step_size = soft_signal_rw(float, initial_value=0.1, units=egu)
            self.integer = soft_signal_rw(int, initial_value=integer)
            self.floating = soft_signal_rw(float, initial_value=floating)
            self.string = soft_signal_rw(str, initial_value=string)
        super().__init__(name=name)
