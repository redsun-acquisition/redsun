"""Tests for the settings tree."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from qtpy import QtWidgets

from redsun.view.qt.treeview import DescriptorTreeView

if TYPE_CHECKING:
    from event_model import Dtype
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
