"""The motors `ophyd-async` ships are axes to the positioner.

Never imported or executed; checked by the project's normal mypy invocation.
"""

from __future__ import annotations

from ophyd_async.epics.demo import DemoMotor
from ophyd_async.epics.motor import Motor

from redsun.utils.devices import Axis

record: Axis = Motor("MOTOR:")
demo: Axis = DemoMotor("DEMO:")
