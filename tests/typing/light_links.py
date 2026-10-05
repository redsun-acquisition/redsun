"""The light stack's signals and slots link to each other.

Never imported or executed; checked by the project's normal mypy invocation.
"""

from __future__ import annotations

from collections.abc import Iterator

from redsun import AsPresenter, AsView, Link, Session
from redsun.presenter import LightPresenter
from redsun.view.qt.builtins import LightView


class Lab(Session):
    lights: AsPresenter[LightPresenter]
    lights_view: AsView[LightView]

    def wire(self) -> Iterator[Link]:
        yield self.lights_view.sig_enabled, self.lights.set_enabled
        yield self.lights_view.sig_intensity, self.lights.set_intensity
        yield self.lights_view.sig_configure, self.lights.configure
        yield self.lights.sig_enabled, self.lights_view.update_enabled
        yield self.lights.sig_intensity, self.lights_view.update_intensity
        yield self.lights.sig_failed, self.lights_view.set_failed
        yield self.lights.sig_configuration, self.lights_view.update_configuration
