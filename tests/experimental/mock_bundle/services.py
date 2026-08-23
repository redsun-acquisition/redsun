from __future__ import annotations

from dishka import Provider, Scope, provide

from redsun.experimental import SessionConfig

from .keys import Calibration


class MockServices(Provider):
    """Shared services this bundle ships, listed in its manifest."""

    scope = Scope.APP

    @provide
    def calibration(self, config: SessionConfig) -> Calibration:
        return Calibration(len(config.session) / 10)
