"""Experimental container layer.

Not covered by any stability guarantee: names and behaviour here may change or
be withdrawn in any release. The supported container layer is
[`redsun.containers`][redsun.containers].

Components are declared as annotations on a container class, each naming the
layer it belongs to, and their dependencies are constructor parameters resolved
by type:

```python
from typing import Annotated

from redsun.experimental import AsDevice, AsPresenter, AsView, Declare
from redsun.experimental.containers.qt import QtAppContainer


class MyApp(QtAppContainer):
    config = "session.yaml"

    stage: AsDevice[MyStage]
    motor_ctrl: AsPresenter[MotorPresenter]
    motor_widget: Annotated[AsView[MotorView], Declare(step_size=5.0)]
```

Requires the ``experimental`` extra (``pip install redsun[experimental]``).
"""

from redsun._hooks import HookError
from redsun._structural import satisfies
from redsun.experimental.containers._declarations import (
    Alias,
    Declare,
    FromConfig,
    Layer,
    Serves,
)
from redsun.experimental.containers._frontend import Frontend
from redsun.experimental.containers._plugins import PluginError
from redsun.experimental.containers._protocols import (
    AttachableComponent,
    NamedComponent,
)
from redsun.experimental.containers.components import (
    AsDevice,
    AsHook,
    AsPresenter,
    AsView,
)
from redsun.experimental.containers.container import AppContainer
from redsun.experimental.view._placement import Placement
from redsun.experimental.virtual._container import (
    BlueskyCallbackRegistry,
    DeviceMapping,
    SessionConfig,
    VirtualContainer,
)
from redsun.experimental.virtual._provides import provides
from redsun.experimental.virtual._requires import (
    DevicesOf,
    Requires,
    RequiresMaybe,
    RequiresOne,
    Satisfying,
)
from redsun.experimental.virtual._wiring import Connection, SessionNotBuilt, slot

__all__ = [
    "Alias",
    "AppContainer",
    "AsDevice",
    "AsHook",
    "AsPresenter",
    "AsView",
    "AttachableComponent",
    "BlueskyCallbackRegistry",
    "Connection",
    "Declare",
    "DeviceMapping",
    "DevicesOf",
    "FromConfig",
    "Frontend",
    "HookError",
    "Layer",
    "NamedComponent",
    "Placement",
    "PluginError",
    "Requires",
    "RequiresMaybe",
    "RequiresOne",
    "Satisfying",
    "Serves",
    "SessionConfig",
    "SessionNotBuilt",
    "VirtualContainer",
    "provides",
    "satisfies",
    "slot",
]
