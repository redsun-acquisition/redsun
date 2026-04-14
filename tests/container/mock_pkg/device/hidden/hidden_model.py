from __future__ import annotations

from typing import Any

from redsun.device import Device


class HiddenModel(Device):
    """Hidden model for testing nested module discovery."""

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
