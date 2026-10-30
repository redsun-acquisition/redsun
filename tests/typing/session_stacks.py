"""A stack declared on a session is typed as its class, and each role as its half.

Never imported or executed; checked by the project's normal mypy invocation.
"""

from __future__ import annotations

from typing import assert_type

from psygnal import Signal

from redsun import AsPresenter, AsStack, AsView, Placement, Session


class Talker:
    sig_said = Signal(str)

    def __init__(self, name: str) -> None:
        self.name = name


class Listener:
    placement: Placement

    def __init__(self, name: str) -> None:
        self.name = name


class Duo:
    presenter: AsPresenter[Talker]
    view: AsView[Listener]


class WithDuo(Session):
    duo: AsStack[Duo]


def check(app: WithDuo) -> None:
    assert_type(app.duo, Duo)
    assert_type(app.duo.presenter, Talker)
    assert_type(app.duo.view, Listener)
