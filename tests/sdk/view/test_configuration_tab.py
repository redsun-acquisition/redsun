"""Tests for the configuration tab."""

from __future__ import annotations

from typing import TypeVar

import pytest
from qtpy import QtCore, QtWidgets

from redsun.utils.devices import Configuration
from redsun.view.qt.treeview import ConfigurationTab, DescriptorTreeView

pytestmark = pytest.mark.qt

T = TypeVar("T", bound=QtCore.QObject)

CONFIGURATION = Configuration(
    descriptors={
        "laser-wavelength": {
            "source": "soft://w:readonly",
            "dtype": "integer",
            "shape": [],
        },
        "led-power": {"source": "soft://p", "dtype": "number", "shape": []},
    },
    readings={
        "laser-wavelength": {"value": 650, "timestamp": 0.0},
        "led-power": {"value": 1.0, "timestamp": 0.0},
    },
    writable={},
)


def child(parent: QtCore.QObject, kind: type[T]) -> T:
    """Return the child of *parent* of type *kind*."""
    found = parent.findChild(kind)
    assert found is not None
    return found


def test_an_edit_is_sent_under_its_key(qapp: QtWidgets.QApplication) -> None:
    """Send an edit of the tree as the full key and the new value."""
    tab = ConfigurationTab(CONFIGURATION)
    sent: list[tuple[str, object]] = []
    tab.sig_configure.connect(lambda *args: sent.append(args))

    child(tab, DescriptorTreeView).sig_property_changed.emit("led", "power", 2.0)

    assert sent == [("led-power", 2.0)]


def test_a_held_owner_cannot_be_edited_until_released(
    qapp: QtWidgets.QApplication,
) -> None:
    """Disable the rows of a held owner, and enable them again after."""
    tab = ConfigurationTab(CONFIGURATION)
    editors = [w for w in tab.findChildren(QtWidgets.QWidget) if w.isEnabled()]

    tab.set_locked(frozenset({"led"}))
    locked = [w for w in editors if not w.isEnabled()]
    tab.set_locked(frozenset())

    assert locked
    assert all(w.isEnabled() for w in editors)


def test_an_empty_configuration_says_so(qapp: QtWidgets.QApplication) -> None:
    """Say there is no configuration when no device has one."""
    tab = ConfigurationTab(Configuration(descriptors={}, readings={}, writable={}))

    assert child(tab, QtWidgets.QLabel).text() == "No device has a configuration."
