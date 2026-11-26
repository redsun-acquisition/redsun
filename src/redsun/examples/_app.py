"""The example session in a window. Needs a Qt binding."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003

from redsun import AsView, Link, Tabs, WindowLayout, links_between
from redsun.qt import QtSession
from redsun.view.qt.builtins import (  # noqa: TC001
    AcquisitionView,
    LightView,
    LogView,
    PositionerView,
)

from ._core import ExampleCore


class ExampleApp(QtSession, ExampleCore):
    """Every built-in component in one window, over simulated devices.

    A stage with two axes, a focus axis, a laser and an LED stand in for
    hardware, so nothing outside the process moves. One plan sends the focus
    to a few positions in turn, and holds it locked while it runs.
    """

    acquisition_view: AsView[AcquisitionView]
    positioner_view: AsView[PositionerView]
    lights_view: AsView[LightView]
    logs: AsView[LogView]

    def window_layout(self) -> WindowLayout:
        """Return the layout the example starts with: the logs as a tab of the centre, the other views docked around it."""
        return WindowLayout({"center": Tabs("logs")})

    def wire(self) -> Iterator[Link]:
        """Link each view to its presenter, and the devices a plan holds to the views that lock them."""
        yield from links_between(self.acquisition_view, self.acquisition)
        yield from links_between(self.positioner_view, self.positioner)
        yield from links_between(self.lights_view, self.lights)
        yield from links_between(self.acquisition, self.positioner_view)
        yield from links_between(self.acquisition, self.lights_view)
        yield from super().wire()
