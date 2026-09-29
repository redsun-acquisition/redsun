"""Tests for the settings tree."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from qtpy import QtWidgets

from redsun.view.qt.treeview import DescriptorTreeView

if TYPE_CHECKING:
    from event_model import DataKey, Dtype
    from qtpy.QtWidgets import QApplication

pytestmark = pytest.mark.qt


def edited_tree() -> tuple[DescriptorTreeView, list[tuple[str, str, Any]]]:
    """Return a tree whose gain the user has just changed from 1 to 100, and what it sent."""
    view = DescriptorTreeView(
        {"cam-gain": {"dtype": "integer", "source": "cam", "shape": []}},
        {"cam-gain": {"value": 1, "timestamp": 0.0}},
    )
    sent: list[tuple[str, str, Any]] = []
    view.sig_property_changed.connect(lambda *args: sent.append(args))
    spinbox = view.findChild(QtWidgets.QSpinBox)
    assert spinbox is not None
    field = spinbox.lineEdit()
    assert field is not None
    field.setText("100")
    spinbox.interpretText()
    return view, sent


def shown(view: DescriptorTreeView) -> int:
    spinbox = view.findChild(QtWidgets.QSpinBox)
    assert spinbox is not None
    return spinbox.value()


@pytest.mark.parametrize(
    ("dtype", "editor", "expected"),
    [
        ("integer", QtWidgets.QSpinBox, 100),
        ("number", QtWidgets.QDoubleSpinBox, 100.0),
    ],
)
def test_a_typed_number_is_sent_once_it_is_entered(
    qapp: QApplication,
    dtype: Dtype,
    editor: type[QtWidgets.QAbstractSpinBox],
    expected: float,
) -> None:
    """Send a typed number once when it is entered, not at each keystroke."""
    view = DescriptorTreeView(
        {"cam-gain": {"dtype": dtype, "source": "cam", "shape": []}},
        {"cam-gain": {"value": 1, "timestamp": 0.0}},
    )
    sent: list[tuple[str, str, Any]] = []
    view.sig_property_changed.connect(lambda *args: sent.append(args))
    spinbox = view.findChild(editor)
    assert spinbox is not None
    field = spinbox.lineEdit()
    assert field is not None

    for text in ("1", "10", "100"):
        field.setText(text)
    spinbox.interpretText()

    assert sent == [("cam", "gain", expected)]


def labels(item: QtWidgets.QTreeWidgetItem) -> list[str]:
    """Return the first-column text of *item*'s children, in order."""
    children = (item.child(i) for i in range(item.childCount()))
    return [child.text(0) for child in children if child is not None]


def test_rows_are_grouped_by_device_and_by_a_property_group(
    qapp: QApplication,
) -> None:
    """Group rows by device, then by the property group in the key."""
    descriptor: DataKey = {"dtype": "string", "source": "pva://x", "shape": []}
    view = DescriptorTreeView(
        {
            "cam-exposure": descriptor,
            "cam-properties-Binning": descriptor,
            "cam-properties-Gain": descriptor,
        },
        {
            "cam-exposure": {"value": "1", "timestamp": 0.0},
            "cam-properties-Binning": {"value": "1", "timestamp": 0.0},
            "cam-properties-Gain": {"value": "0", "timestamp": 0.0},
        },
    )

    assert view.topLevelItemCount() == 1
    cam = view.topLevelItem(0)
    assert cam is not None and cam.text(0) == "cam"
    assert labels(cam) == ["exposure", "properties"]
    properties = cam.child(1)
    assert properties is not None
    assert labels(properties) == ["Binning", "Gain"]


@pytest.mark.parametrize("source", ["soft://readonly", "pva://cam:readonly"])
def test_a_read_only_source_gives_a_label_not_an_editor(
    qapp: QApplication, source: str
) -> None:
    """Show a value from a read-only source as a label, not an editor."""
    view = DescriptorTreeView(
        {"cam-dtype": {"dtype": "string", "source": source, "shape": []}},
        {"cam-dtype": {"value": "uint8", "timestamp": 0.0}},
    )

    assert view.findChild(QtWidgets.QLineEdit) is None
    label = view.findChild(QtWidgets.QLabel)
    assert label is not None and label.text() == "uint8"


def test_an_edit_shows_what_the_device_read_back(qapp: QApplication) -> None:
    """Show the value the device read back and ignore a late refusal."""
    view, sent = edited_tree()

    view.set_value("cam-gain", 64)
    view.revert("cam-gain")

    assert shown(view) == 64
    assert sent == [("cam", "gain", 100)]


def test_a_refused_edit_shows_the_value_before_it(qapp: QApplication) -> None:
    """Show the previous value again when an edit is refused."""
    view, sent = edited_tree()

    view.revert("cam-gain")

    assert shown(view) == 1
    assert sent == [("cam", "gain", 100)]


def test_a_value_changing_with_no_edit_pending_is_shown(qapp: QApplication) -> None:
    """Show a new value with no edit pending and ignore an unknown key."""
    view = DescriptorTreeView(
        {"cam-gain": {"dtype": "integer", "source": "cam", "shape": []}},
        {"cam-gain": {"value": 1, "timestamp": 0.0}},
    )

    view.set_value("cam-gain", 7)
    view.set_value("cam-missing", 3)

    assert shown(view) == 7
