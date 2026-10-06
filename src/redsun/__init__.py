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

from redsun.errors import (
    BuildError,
    ConfigurationError,
    ConfigurationInUse,
    HookError,
    PluginError,
)
from redsun.injection import (
    DevicesOf,
    provides,
    rejected,
    satisfying,
)
from redsun.ports import (
    ComponentNotBuilt,
    Connection,
    Link,
    WiringError,
    links_between,
    slot,
)
from redsun.registry import (
    CallbackType,
    DeviceMapping,
    HasActions,
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
    Serializable,
    Serves,
    Session,
)
from redsun.view import Placement

from ._hooks import (
    ConfiguresApplication,
    ConfiguresMainView,
    ConfirmsClose,
    CreatesApplication,
    WrapsBuild,
)
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
    "BuildError",
    "BuildableSession",
    "CallbackType",
    "ComponentNotBuilt",
    "ConfigurationError",
    "ConfigurationInUse",
    "ConfiguresApplication",
    "ConfiguresMainView",
    "ConfirmsClose",
    "Connection",
    "CreatesApplication",
    "Declare",
    "DesktopSession",
    "DeviceMapping",
    "DevicesOf",
    "FromConfig",
    "Frontend",
    "HasActions",
    "HasAsyncShutdown",
    "HasPlans",
    "HasSetup",
    "HasShutdown",
    "HookError",
    "Launch",
    "Layer",
    "Link",
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
    "WrapsBuild",
    "__version__",
    "links_between",
    "provides",
    "rejected",
    "satisfies",
    "satisfying",
    "slot",
]
