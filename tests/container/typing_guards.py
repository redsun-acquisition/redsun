"""Static guards for component attribute typing.

Not collected by pytest: the assertions are the ``type: ignore`` comments, which
``warn_unused_ignores`` turns into mypy errors if the annotations ever stop
catching these. Run through the normal ``uv run mypy`` invocation.
"""

from __future__ import annotations

from mock_pkg.controller.mock_presenters import AsyncMotorController, MockController

from redsun.containers import AppContainer, declare_presenter, declare_view
from redsun.view import PView, ViewPosition


class _Widget:
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def view_position(self) -> ViewPosition:
        return ViewPosition.CENTER


class _Typed(AppContainer):
    mover = declare_presenter(AsyncMotorController)
    ctrl = declare_presenter(MockController)
    widget = declare_view(_Widget)

    def wire(self) -> None:
        # the declared type is the component class, not Any
        signal: object = self.mover.sig_motor_moved
        del signal

        # a port the class does not have is an error, not a build-time surprise
        self.mover.sig_typo  # type: ignore[attr-defined]
        self.ctrl.on_typo  # type: ignore[attr-defined]
        self.widget.missing  # type: ignore[attr-defined]


def _resolves_to_the_component_class(app: _Typed) -> None:
    mover: AsyncMotorController = app.mover
    ctrl: MockController = app.ctrl
    widget: _Widget = app.widget
    del mover, ctrl, widget


def _view_satisfies_its_protocol(app: _Typed) -> PView:
    return app.widget
