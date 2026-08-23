"""A layer marker types the attribute as the component, not as a wrapper.

Never imported or executed: pytest skips it and mypy checks it through
``files = "."``. Whether a class satisfies `PView` or `PPresenter` is a
structural question, so only a type checker observes the answer here; the
container asks the same question again at runtime.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import assert_type

from redsun.experimental import AsPresenter, AsView, Placement, PPresenter, PView
from redsun.experimental.qt import Central, Dock, QtAppContainer


class Ctrl:
    def __init__(self, name: str, /) -> None:
        self.name = name


class Panel:
    placement: Placement = Dock("left")

    def __init__(self, name: str, /) -> None:
        self.name = name


class Canvas:
    def __init__(self, name: str, /) -> None:
        self.name = name

    @property
    def placement(self) -> Placement:
        return Central()


class App(QtAppContainer):
    __slots__ = ()

    ctrl: AsPresenter[Ctrl]
    panel: AsView[Panel]
    canvas: AsView[Canvas]


def check(app: App) -> None:
    assert_type(app.ctrl, Ctrl)
    assert_type(app.panel, Panel)
    assert_type(app.views, Mapping[str, PView])
    assert_type(app.presenters, Mapping[str, PPresenter])


def check_structurally(app: App) -> None:
    """Pin that a class attribute and a property both answer ``placement``."""
    from_attribute: PView = app.panel
    from_property: PView = app.canvas
    presenter: PPresenter = app.ctrl
    assert_type(from_attribute.placement, Placement)
    assert_type(from_property.placement, Placement)
    assert_type(presenter.name, str)
