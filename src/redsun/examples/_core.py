"""The devices and presenters of the example session, whatever frontend shows them."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003
from typing import Any, ClassVar

from redsun import AsDevice, AsPresenter, Link, Session, links_between
from redsun.presenter import (  # noqa: TC001
    AcquisitionPresenter,
    LightPresenter,
    PositionerPresenter,
)

from ._devices import Axis, Laser, Led, Plans, Stage  # noqa: TC001


class ExampleCore(Session):
    """The devices and presenters of the example, and the links between presenters.

    A stage with two axes, a focus axis, a laser and an LED stand in for
    hardware, so nothing outside the process moves. One plan sends the focus
    to a few positions in turn, and holds it locked while it runs.
    """

    config: ClassVar[dict[str, Any]] = {"session": "redsun-example", "strict": True}

    stage: AsDevice[Stage]
    focus: AsDevice[Axis]
    laser: AsDevice[Laser]
    led: AsDevice[Led]

    plans: AsPresenter[Plans]
    acquisition: AsPresenter[AcquisitionPresenter]
    positioner: AsPresenter[PositionerPresenter]
    lights: AsPresenter[LightPresenter]

    def wire(self) -> Iterator[Link]:
        """Link the acquisition to the devices a plan holds, through their presenters."""
        yield from links_between(self.acquisition, self.positioner)
        yield from links_between(self.acquisition, self.lights)
