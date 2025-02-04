"""Common reusable view functions for Qt framework."""

from __future__ import annotations

from typing import Optional

from qtpy import QtWidgets


def ask_file_path(
    parent: QtWidgets.QWidget,
    title: str,
    file_filter: str,
    *,
    folder: Optional[str] = None,
    saving: bool = True,
) -> Optional[str]:
    """Ask the user for a file path.

    Parameters
    ----------
    parent : QtWidgets.QWidget
        Parent widget making the request.
    title : str
        Dialog title.
    file_filter : str
        File filter.
    folder : str, optional
        Folder to open the dialog in.
        Default is None.
    saving : bool, optional
        True if the dialog is for saving a file, False otherwise.
        Default is True.
    """
    if saving:
        dialog = QtWidgets.QFileDialog.getSaveFileName
    else:
        dialog = QtWidgets.QFileDialog.getOpenFileName
    path, _ = dialog(parent=parent, caption=title, directory=folder, filter=file_filter)
    return path if path else None
