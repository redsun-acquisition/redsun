"""The layer a declared component belongs to.

Each alias annotates the component's own type, so the attribute stays typed as
what it holds:

```python
from redsun.experimental import Session, AsDevice, AsPresenter, AsView


class MyApp(Session):
    stage: AsDevice[MyStage]
    motor_ctrl: AsPresenter[MotorPresenter]
    motor_widget: AsView[MotorView]
```

A declaration must carry one: an annotation without a layer is an ordinary
attribute. The names are prefixed so that they say what they mark, and so that
they collide with nothing a component may itself subclass.
"""

from __future__ import annotations

from typing import Annotated, TypeAlias, TypeVar

from redsun.services import Service

from ._declarations import Hook, Layer, ServiceMark

__all__ = ["AsDevice", "AsHook", "AsPresenter", "AsService", "AsView"]

T = TypeVar("T")

AsDevice: TypeAlias = Annotated[T, Layer.DEVICE]
"""An `ophyd_async.core.Device`, built before every other layer."""

AsPresenter: TypeAlias = Annotated[T, Layer.PRESENTER]
"""A component holding application logic, taking ``name`` first.

Satisfies `redsun.experimental.NamedComponent`, and declares no placement.
"""

AsView: TypeAlias = Annotated[T, Layer.VIEW]
"""A component presenting an interface, taking ``name`` first.

Satisfies `redsun.experimental.AttachableComponent`, so it declares the
`redsun.experimental.Placement` it asks the frontend to attach it at.
"""


AsService: TypeAlias = Annotated[Service, ServiceMark()]
"""A server the session's devices talk to, started before any component is built.

`redsun.experimental.Launch` describes a service the session runs, and
`redsun.experimental.Attach` one already running elsewhere. Without either,
the service comes from the session's ``services`` entry for it. An alias
carrying the marker can be declared once and used by several sessions:

```python
CameraIoc: TypeAlias = Annotated[
    AsService, Launch("mylab.iocs.camera", ready="Server startup complete.", prefix="CAM:")
]


class MyApp(Session):
    camera_ioc: CameraIoc
```
"""


AsHook: TypeAlias = Annotated[T, Hook()]
"""A callback the session calls at one point of the toolkit's startup.

The attribute name is the point, `redsun.experimental.Serves` names them
instead, and `redsun.experimental.Declare` carries the constructor arguments.
A hook is not a component: it is never injected, nothing may depend on it, and
it has no say in what the session builds.
"""
