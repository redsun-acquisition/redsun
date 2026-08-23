"""Experimental container layer, built on dishka.

Not covered by any stability guarantee: names and behaviour here may change or
be withdrawn in any release. The supported container layer is
[`redsun.containers`][redsun.containers].

Components are declared as annotations on a container class, each naming the
layer it belongs to, and their dependencies are constructor parameters resolved
by type:

```python
from typing import Annotated

from redsun.experimental import AsDevice, AsPresenter, AsView, Declare
from redsun.experimental.qt import QtAppContainer


class MyApp(QtAppContainer):
    config = "session.yaml"

    stage: AsDevice[MyStage]
    motor_ctrl: AsPresenter[MotorPresenter]
    motor_widget: Annotated[AsView[MotorView], Declare(step_size=5.0)]
```

Requires the ``experimental`` extra (``pip install redsun[experimental]``).
"""

from redsun.experimental._container import AppContainer
from redsun.experimental._declarations import (
    Alias,
    Declare,
    FromConfig,
    Layer,
)
from redsun.experimental._frontend import Frontend, check_placement
from redsun.experimental._placement import Placement
from redsun.experimental._plugins import PluginError
from redsun.experimental._protocols import PPresenter, PView
from redsun.experimental._provides import provides
from redsun.experimental._requires import (
    DevicesOf,
    Requires,
    RequiresMaybe,
    RequiresOne,
    Satisfying,
)
from redsun.experimental._structural import satisfies
from redsun.experimental._virtual import (
    DeviceMapping,
    DocumentCallbacks,
    SessionConfig,
    VirtualContainer,
)
from redsun.experimental._wiring import Connection, slot
from redsun.experimental.layer import AsDevice, AsPresenter, AsView

__all__ = [
    "Alias",
    "AppContainer",
    "AsDevice",
    "AsPresenter",
    "AsView",
    "Connection",
    "Declare",
    "DeviceMapping",
    "DevicesOf",
    "DocumentCallbacks",
    "FromConfig",
    "Frontend",
    "Layer",
    "PPresenter",
    "PView",
    "Placement",
    "PluginError",
    "Requires",
    "RequiresMaybe",
    "RequiresOne",
    "Satisfying",
    "SessionConfig",
    "VirtualContainer",
    "check_placement",
    "provides",
    "satisfies",
    "slot",
]
