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

from redsun.experimental._declarations import Layer

__all__ = ["AsDevice", "AsPresenter", "AsView"]

T = TypeVar("T")

AsDevice: TypeAlias = Annotated[T, Layer.DEVICE]
"""An `ophyd_async.core.Device`, built before every other layer."""

AsPresenter: TypeAlias = Annotated[T, Layer.PRESENTER]
"""A component holding application logic, taking ``name`` first.

Satisfies `redsun.experimental.PPresenter`, and declares no placement.
"""

AsView: TypeAlias = Annotated[T, Layer.VIEW]
"""A component presenting an interface, taking ``name`` first.

Satisfies `redsun.experimental.PView`, so it declares the
`redsun.experimental.Placement` it asks the frontend to attach it at.
"""
