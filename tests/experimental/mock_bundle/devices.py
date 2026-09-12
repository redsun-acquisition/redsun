from __future__ import annotations

from ophyd_async.core import Device


class MockStage(Device):
    """Device carrying a configured keyword argument."""

    def __init__(self, name: str, /, axis: str = "X") -> None:
        super().__init__(name=name)
        self.axis = axis
