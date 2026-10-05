"""The positioner's signals and slots link to each other.

Never imported or executed; checked by the project's normal mypy invocation.
"""

from __future__ import annotations

from collections.abc import Iterator

from redsun import AsPresenter, AsView, Link, Session
from redsun.presenter import PositionerPresenter
from redsun.view.qt.builtins import PositionerView


class Lab(Session):
    positioner: AsPresenter[PositionerPresenter]
    positioner_view: AsView[PositionerView]

    def wire(self) -> Iterator[Link]:
        yield self.positioner_view.sig_move, self.positioner.move
        yield self.positioner_view.sig_move_to, self.positioner.move_to
        yield self.positioner.sig_readback, self.positioner_view.update_readback
        yield self.positioner.sig_moving, self.positioner_view.set_moving
        yield self.positioner.sig_failed, self.positioner_view.set_failed
        yield self.positioner.sig_limits, self.positioner_view.update_limits
        yield self.positioner_view.sig_stop, self.positioner.stop
        yield self.positioner_view.sig_configure, self.positioner.configure
        yield (
            self.positioner.sig_configuration,
            self.positioner_view.update_configuration,
        )
