"""Tests for the configuration tab."""

from __future__ import annotations

import pytest
from qtpy import QtCore, QtWidgets

from redsun.utils.devices import Configuration, DevicePath
from redsun.view.qt.treeview import ConfigurationTab

pytestmark = pytest.mark.qt

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


UNDERSCORED = Configuration(
    descriptors={
        "scope_xy_x_velocity": {"source": "soft://v", "dtype": "number", "shape": []}
    },
    readings={"scope_xy_x_velocity": {"value": 1.0, "timestamp": 0.0}},
    writable={},
    owners={"scope_xy_x_velocity": "scope_xy"},
    paths={
        "scope_xy_x_velocity": DevicePath(
            "scope",
            "xy.x.velocity",
            ("scope", "scope_xy", "scope_xy_x", "scope_xy_x_velocity"),
        ),
        "scope_xy": DevicePath("scope", "xy", ("scope", "scope_xy")),
    },
)


def editor(tab: ConfigurationTab, owner: str) -> QtWidgets.QWidget:
    """Return the editor of the one setting of *owner* in *tab*."""
    [row] = tab.findItems(owner, QtCore.Qt.MatchFlag.MatchExactly)
    setting = row.child(0)
    assert setting is not None
    widget = tab.itemWidget(setting, 1)
    assert widget is not None
    return widget


def test_an_edit_is_sent_under_its_key(qapp: QtWidgets.QApplication) -> None:
    """Send an edit of the tree as the full key and the new value."""
    tab = ConfigurationTab(CONFIGURATION)
    sent: list[tuple[str, object]] = []
    tab.sig_configure.connect(lambda *args: sent.append(args))
    power = editor(tab, "led")
    assert isinstance(power, QtWidgets.QDoubleSpinBox)

    power.setValue(2.0)

    assert sent == [("led-power", 2.0)]


def test_a_held_owner_cannot_be_edited_until_released(
    qapp: QtWidgets.QApplication,
) -> None:
    """Disable the rows of a held owner only, and enable them again after."""
    tab = ConfigurationTab(CONFIGURATION)
    power, wavelength = editor(tab, "led"), editor(tab, "laser")

    tab.set_locked(frozenset({"led"}))
    locked = (power.isEnabled(), wavelength.isEnabled())
    tab.set_locked(frozenset())

    assert locked == (False, True)
    assert power.isEnabled()


def test_an_empty_configuration_says_so(qapp: QtWidgets.QApplication) -> None:
    """Say there is no configuration when no device has one."""
    tab = ConfigurationTab(Configuration(descriptors={}, readings={}, writable={}))
    row = tab.topLevelItem(0)

    assert row is not None
    assert row.text(0) == "No device has a configuration."
    assert not row.flags() & QtCore.Qt.ItemFlag.ItemIsSelectable


def test_an_owner_named_with_a_dash_is_kept_whole(
    qapp: QtWidgets.QApplication,
) -> None:
    """Group and lock the rows of an owner whose name holds a dash."""
    key = "laser-488-wavelength"
    tab = ConfigurationTab(
        Configuration(
            descriptors={key: {"source": "soft://w", "dtype": "integer", "shape": []}},
            readings={key: {"value": 488, "timestamp": 0.0}},
            writable={},
            owners={key: "laser-488"},
        )
    )
    row = tab.topLevelItem(0)
    editors = [w for w in tab.findChildren(QtWidgets.QWidget) if w.isEnabled()]

    tab.set_locked(frozenset({"laser-488"}))
    locked = [w for w in editors if not w.isEnabled()]

    assert row is not None
    assert row.text(0) == "laser-488"
    assert locked


def test_a_row_is_named_by_its_path_and_edits_its_own_key(
    qapp: QtWidgets.QApplication,
) -> None:
    """Show a row's path below its owner's, and send an edit under the row's key."""
    tab = ConfigurationTab(UNDERSCORED)
    sent: list[tuple[str, object]] = []
    tab.sig_configure.connect(lambda *args: sent.append(args))

    [owner] = tab.findItems("scope / xy", QtCore.Qt.MatchFlag.MatchExactly)
    row = owner.child(0)
    assert row is not None
    velocity = tab.itemWidget(row, 1)
    assert isinstance(velocity, QtWidgets.QDoubleSpinBox)
    velocity.setValue(2.0)

    assert row.text(0) == "x.velocity"
    assert sent == [("scope_xy_x_velocity", 2.0)]


@pytest.mark.parametrize(
    ("held", "enabled"),
    [({"scope_xy_x"}, False), ({"scope"}, False), ({"scope_xy_y"}, True)],
)
def test_a_row_below_a_held_device_cannot_be_edited(
    qapp: QtWidgets.QApplication, held: set[str], enabled: bool
) -> None:
    """Disable a row when a device above its signal is held, and only then."""
    tab = ConfigurationTab(UNDERSCORED)

    tab.set_locked(frozenset(held))

    [owner] = tab.findItems("scope / xy", QtCore.Qt.MatchFlag.MatchExactly)
    row = owner.child(0)
    assert row is not None
    velocity = tab.itemWidget(row, 1)
    assert velocity is not None
    assert velocity.isEnabled() is enabled
