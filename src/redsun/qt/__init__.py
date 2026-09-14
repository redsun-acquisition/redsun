"""Qt public API of ``redsun``: the Qt application container and hook aliases.

Examples
--------
>>> from redsun.containers import declare_device
>>> from redsun.qt import QtAppContainer

>>> class MyApp(QtAppContainer, config="config.yaml"):
...     motor = declare_device(MyMotor, from_config="motor")
"""

from __future__ import annotations

from redsun.containers.qt import (
    QtAppContainer,
    QtConfiguresApplication,
    QtConfiguresMainView,
    QtCreatesApplication,
    QtWrapsBuild,
)

__all__ = [
    "QtAppContainer",
    "QtConfiguresApplication",
    "QtConfiguresMainView",
    "QtCreatesApplication",
    "QtWrapsBuild",
]
