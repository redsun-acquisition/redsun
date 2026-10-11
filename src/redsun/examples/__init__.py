"""An example session holding every built-in component, over simulated devices."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003
from typing import Any, ClassVar

from redsun import AsDevice, AsPresenter, AsView, Link, links_between
from redsun.presenter import (  # noqa: TC001
    AcquisitionPresenter,
    LightPresenter,
    PositionerPresenter,
)
from redsun.qt import QtSession
from redsun.view.qt.builtins import (  # noqa: TC001
    AcquisitionView,
    LightView,
    LogView,
    PositionerView,
)

from ._devices import Laser, Led, Plans, Stage  # noqa: TC001

__all__ = ["ExampleApp", "example_config"]


def example_config(style: str | None) -> dict[str, Any]:
    """Return the configuration showing the example in *style*, or in the platform's look for `None`.

    *style* is the short name of a style `redsun` ships, as a session file
    writes it.
    """
    if style is None:
        return {}
    return {"hooks": {"configure_application": style}}


class ExampleApp(QtSession):
    """Every built-in component in one window, over simulated devices.

    A stage with two axes, a laser and an LED stand in for hardware, and one
    plan walks an axis. Nothing is written or moved outside the process.
    """

    config: ClassVar[dict[str, Any]] = {"session": "redsun-example", "strict": True}

    stage: AsDevice[Stage]
    laser: AsDevice[Laser]
    led: AsDevice[Led]

    plans: AsPresenter[Plans]
    acquisition: AsPresenter[AcquisitionPresenter]
    positioner: AsPresenter[PositionerPresenter]
    lights: AsPresenter[LightPresenter]

    acquisition_view: AsView[AcquisitionView]
    positioner_view: AsView[PositionerView]
    lights_view: AsView[LightView]
    logs: AsView[LogView]

    def wire(self) -> Iterator[Link]:
        """Link each view to its presenter, and the devices a plan holds to the views that lock them."""
        yield from links_between(self.acquisition_view, self.acquisition)
        yield from links_between(self.positioner_view, self.positioner)
        yield from links_between(self.lights_view, self.lights)
        yield from links_between(self.acquisition, self.positioner)
        yield from links_between(self.acquisition, self.positioner_view)
        yield from links_between(self.acquisition, self.lights)
        yield from links_between(self.acquisition, self.lights_view)
