from __future__ import annotations

from typing import Annotated

from redsun import AsPresenter, AsView, Declare

from .presenters import MockMotorPresenter
from .views import MockMotorView


class MockMotorStack:
    """The mock motor presenter with a view and a detail view."""

    presenter: AsPresenter[MockMotorPresenter]
    view: AsView[MockMotorView]
    detail: Annotated[AsView[MockMotorView], Declare(title="detail")]
