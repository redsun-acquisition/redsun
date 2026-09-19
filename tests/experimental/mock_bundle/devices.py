from __future__ import annotations

from ophyd_async.core import StandardReadable, StandardReadableFormat, soft_signal_rw


class MockStage(StandardReadable):
    """Device holding its configured axis in a configuration signal."""

    def __init__(self, name: str, axis: str = "X") -> None:
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.axis = soft_signal_rw(str, initial_value=axis)
        super().__init__(name=name)
