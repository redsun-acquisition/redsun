"""Experimental session layer.

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

from redsun.experimental.injection import (
    DevicesOf,
    provides,
    rejected,
    satisfying,
)
from redsun.experimental.ports import (
    ComponentNotBuilt,
    Connection,
    WiringError,
    slot,
)
from redsun.experimental.registry import (
    CallbackType,
    DeviceMapping,
    HasPlans,
    PlanEntry,
    SessionConfig,
)
from redsun.experimental.session import (
    Alias,
    AsDevice,
    AsHook,
    AsPresenter,
    AsService,
    AsView,
    Attach,
    AttachableComponent,
    BuildableSession,
    ConfigurationInUse,
    Declare,
    DesktopSession,
    FromConfig,
    Frontend,
    HasAsyncShutdown,
    HasSetup,
    HasShutdown,
    Launch,
    Layer,
    NamedComponent,
    PluginError,
    Serializable,
    Serves,
    Session,
)
from redsun.experimental.view import Placement

from .._config import ConfigurationError
from .._hooks import ConfirmsClose, HookError
from .._structural import satisfies
from ._settings import Settings

__all__ = [
    "Alias",
    "AsDevice",
    "AsHook",
    "AsPresenter",
    "AsService",
    "AsView",
    "Attach",
    "AttachableComponent",
    "BuildableSession",
    "CallbackType",
    "ComponentNotBuilt",
    "ConfigurationError",
    "ConfigurationInUse",
    "ConfirmsClose",
    "Connection",
    "Declare",
    "DesktopSession",
    "DeviceMapping",
    "DevicesOf",
    "FromConfig",
    "Frontend",
    "HasAsyncShutdown",
    "HasPlans",
    "HasSetup",
    "HasShutdown",
    "HookError",
    "Launch",
    "Layer",
    "NamedComponent",
    "Placement",
    "PlanEntry",
    "PluginError",
    "Serializable",
    "Serves",
    "Session",
    "SessionConfig",
    "Settings",
    "WiringError",
    "provides",
    "rejected",
    "satisfies",
    "satisfying",
    "slot",
]
