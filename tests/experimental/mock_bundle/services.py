from __future__ import annotations

from redsun.experimental import SessionConfig, provides

from .keys import Calibration


class MockServices:
    """Shared services this bundle ships, listed in its manifest."""

    def __init__(self, config: SessionConfig) -> None:
        self._config = config

    @provides
    def calibration(self) -> Calibration:
        """Derive a calibration from the session the bundle was installed into."""
        return Calibration(len(self._config.name) / 10)
