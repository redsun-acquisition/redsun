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
    """Typing "100" sends 100, not 1 then 10 then 100."""
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
    """``cam-properties-Binning`` sits under ``properties`` under ``cam``."""
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
