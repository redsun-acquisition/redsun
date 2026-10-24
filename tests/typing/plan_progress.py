"""A progress scope reports values of the type of the status it follows.

Never imported or executed; checked by the project's normal mypy invocation.
A scope named without a type reports values of any type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, assert_type

import redsun.engine.plan_stubs as rps
from redsun.engine import PlanProgress

if TYPE_CHECKING:
    from bluesky.protocols import Status
    from bluesky.utils import MsgGenerator
    from ophyd_async.core import WatchableAsyncStatus


def follow(
    watched: WatchableAsyncStatus[float], plain: Status, scope: PlanProgress
) -> None:
    assert_type(
        rps.monitor_progress("move", watched), MsgGenerator[PlanProgress[float]]
    )
    assert_type(rps.monitor_progress("move", plain), MsgGenerator[PlanProgress[Any]])
    assert_type(scope, PlanProgress[Any])
