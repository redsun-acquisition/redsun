"""Experimental session layer.

Not covered by any stability guarantee: names and behaviour here may change or
be withdrawn in any release. The supported container layer is
[`redsun.containers`][redsun.containers].

Components are declared as annotations on a session class, each naming the
layer it belongs to, and their dependencies are constructor parameters resolved
by type:

```python
from typing import Annotated

from redsun.experimental import AsDevice, AsPresenter, AsView, Declare
from redsun.experimental.session.qt import QtSession


class MyApp(QtSession):
    config = "session.yaml"

    stage: AsDevice[MyStage]
    motor_ctrl: AsPresenter[MotorPresenter]
    motor_widget: Annotated[AsView[MotorView], Declare(step_size=5.0)]
```

Requires the ``experimental`` extra (``pip install redsun[experimental]``).
"""

from redsun._hooks import ConfirmsClose, HookError
from redsun._structural import satisfies
from redsun.experimental._settings import Settings
from redsun.experimental.session import (
    Alias,
    AsDevice,
    AsHook,
    AsPresenter,
    AsView,
    AttachableComponent,
    BuildableSession,
    ConfigurationInUse,
    Declare,
    DesktopSession,
    FromConfig,
    Frontend,
    Layer,
    NamedComponent,
    PluginError,
    Serializable,
    Serves,
    Session,
)
from redsun.experimental.view._placement import Placement
from redsun.experimental.virtual._provides import provides
from redsun.experimental.virtual._requires import (
    DevicesOf,
    Requires,
    RequiresMaybe,
    RequiresOne,
    Satisfying,
)
from redsun.experimental.virtual._shared import (
    BlueskyCallbackRegistry,
    DeviceMapping,
    SessionConfig,
)
from redsun.experimental.virtual._wiring import (
    ComponentNotBuilt,
    Connection,
    SessionNotBuilt,
    WiringError,
    slot,
)

__all__ = [
    "Alias",
    "AsDevice",
    "AsHook",
    "AsPresenter",
    "AsView",
    "AttachableComponent",
    "BlueskyCallbackRegistry",
    "BuildableSession",
    "ComponentNotBuilt",
    "ConfigurationInUse",
    "ConfirmsClose",
    "Connection",
    "Declare",
    "DesktopSession",
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
    "Serializable",
    "Serves",
    "Session",
    "SessionConfig",
    "SessionNotBuilt",
    "Settings",
    "WiringError",
    "provides",
    "satisfies",
    "slot",
]
