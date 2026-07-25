from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qtpy import QtWidgets

from redsun.common.qt import ask_file_path

if TYPE_CHECKING:
    from typing import Any


@pytest.mark.qt
def test_ask_file_path_save_returns_selection(
    qapp: QtWidgets.QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_dialog(*args: Any) -> tuple[str, str]:
        return ("C:/data/out.h5", "*.h5")

    monkeypatch.setattr(
        QtWidgets.QFileDialog, "getSaveFileName", staticmethod(fake_dialog)
    )
    parent = QtWidgets.QWidget()
    assert ask_file_path(parent, "Save", "*.h5", folder=".") == "C:/data/out.h5"


@pytest.mark.qt
def test_ask_file_path_open_cancelled_returns_none(
    qapp: QtWidgets.QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_dialog(*args: Any) -> tuple[str, str]:
        return ("", "")

    monkeypatch.setattr(
        QtWidgets.QFileDialog, "getOpenFileName", staticmethod(fake_dialog)
    )
    parent = QtWidgets.QWidget()
    assert ask_file_path(parent, "Open", "*.h5", folder=".", saving=False) is None
