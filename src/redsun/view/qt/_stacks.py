from __future__ import annotations

from redsun.presenter import AcquisitionPresenter, LightPresenter, PositionerPresenter  # noqa: TC001
from redsun.session import AsPresenter, AsView  # noqa: TC001

from ._acquisition_view import AcquisitionView  # noqa: TC001
from ._light_view import LightView  # noqa: TC001
from ._positioner_view import PositionerView  # noqa: TC001

__all__ = ["AcquisitionStack", "LightStack", "PositionerStack"]


class AcquisitionStack:
    """The acquisition presenter with its view."""

    presenter: AsPresenter[AcquisitionPresenter]
    view: AsView[AcquisitionView]


class PositionerStack:
    """The positioner presenter with its view."""

    presenter: AsPresenter[PositionerPresenter]
    view: AsView[PositionerView]


class LightStack:
    """The light presenter with its view."""

    presenter: AsPresenter[LightPresenter]
    view: AsView[LightView]
