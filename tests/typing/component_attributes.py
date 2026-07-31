"""Type-level assertions for the container's declarative fields.

Never imported or executed: each function body is a set of `assert_type` calls
that a type checker verifies. `assert_type` demands the inferred type match
exactly, so an attribute that falls back to `Any` fails here even though it
would pass every runtime test.

Checked by the project's normal mypy invocation; see CLAUDE.md.
"""

from __future__ import annotations

from typing import assert_type

from mock_pkg.controller.mock_presenters import (
    AsyncMotorController,
    GroupedController,
    MockController,
)
from mock_pkg.device.mock_motors import MyMotor
from mock_pkg.view.mock_views import MockMotorView
from psygnal import SignalInstance

from redsun.containers import (
    AppContainer,
    declare_device,
    declare_presenter,
    declare_view,
)


class _App(AppContainer):
    motor = declare_device(MyMotor)
    mover = declare_presenter(AsyncMotorController)
    ctrl = declare_presenter(MockController, alias="controller")
    grouped = declare_presenter(GroupedController)
    widget = declare_view(MockMotorView)


def check_declared_attributes_keep_their_class(app: _App) -> None:
    assert_type(app.motor, MyMotor)
    assert_type(app.mover, AsyncMotorController)
    assert_type(app.ctrl, MockController)
    assert_type(app.widget, MockMotorView)


def check_alias_and_kwargs_do_not_erase_the_type(app: _App) -> None:
    assert_type(declare_presenter(MockController, alias="other"), MockController)
    assert_type(declare_presenter(MockController, gain=1.0), MockController)
    assert_type(declare_device(MyMotor, from_config="motor"), MyMotor)


def check_ports_resolve_through_the_attribute(app: _App) -> None:
    assert_type(app.mover.sig_motor_moved, SignalInstance)
    assert_type(app.grouped.frames.median, SignalInstance)


def check_wire_is_ordinary_checked_code(app: _App) -> None:
    # the two ends of a connection are resolved, not Any: naming a port that
    # does not exist is an attr-defined error rather than a build failure
    app.connect(app.mover.sig_motor_moved, app.ctrl.on_motor_moved)
