"""The layer a declared component belongs to.

Each alias annotates the component's own type, so the attribute stays typed as
what it holds:

```python
from redsun.experimental import AppContainer, AsDevice, AsPresenter, AsView


class MyApp(AppContainer):
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

from redsun.experimental.containers._declarations import Hook, Layer

__all__ = ["AsDevice", "AsHook", "AsPresenter", "AsView"]

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


AsHook: TypeAlias = Annotated[T, Hook()]
"""A callback the container calls at one point of the toolkit's startup.

The attribute name is the point, `redsun.experimental.Serves` names them
instead, and `redsun.experimental.Declare` carries the constructor arguments.
A hook is not a component: it is never injected, nothing may depend on it, and
it has no say in what the container builds.
"""
