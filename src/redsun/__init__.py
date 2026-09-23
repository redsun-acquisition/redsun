"""Build acquisition applications from declared components.

Components are declared as annotations on a session class, each naming the
layer it belongs to, and their dependencies are constructor parameters resolved
by type:

```python
from typing import Annotated

from redsun import AsDevice, AsPresenter, AsView, Declare
from redsun.qt import QtSession


class MyApp(QtSession):
    config = "session.yaml"

    stage: AsDevice[MyStage]
    motor_ctrl: AsPresenter[MotorPresenter]
    motor_widget: Annotated[AsView[MotorView], Declare(step_size=5.0)]
```
"""

from importlib.metadata import PackageNotFoundError, version

from redsun.injection import (
    DevicesOf,
    provides,
    rejected,
    satisfying,
)
from redsun.ports import (
    ComponentNotBuilt,
    Connection,
    WiringError,
    slot,
)
from redsun.registry import (
    CallbackType,
    DeviceMapping,
    HasPlans,
    PlanEntry,
    SessionConfig,
)
from redsun.session import (
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
from redsun.view import Placement

from ._config import ConfigurationError
from ._hooks import ConfirmsClose, HookError
from ._settings import Settings
from ._structural import satisfies

try:
    __version__ = version("redsun")
except PackageNotFoundError:
    __version__ = "unknown"

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
    "__version__",
    "provides",
    "rejected",
    "satisfies",
    "satisfying",
    "slot",
]
