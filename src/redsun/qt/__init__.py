"""Qt-specific public API for Redsun.

Exposes the Qt application container for use in explicit,
developer-written application configurations.

Examples
--------
>>> from redsun.qt import QtAppContainer
>>> from redsun import AppContainer, component

>>> class MyApp(QtAppContainer, config="config.yaml"):
...     motor = component(MyMotor, layer="device", from_config="motor")
"""

from __future__ import annotations

from redsun.containers.qt_container import QtAppContainer

__all__ = ["QtAppContainer"]
