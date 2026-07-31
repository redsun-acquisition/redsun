"""Common reusable view functions for Qt framework."""

from __future__ import annotations

from qtpy import QtWidgets


def ask_file_path(
    parent: QtWidgets.QWidget,
    title: str,
    file_filter: str,
    *,
    folder: str,
    saving: bool = True,
) -> str | None:
    """Ask the user for a file path.

    Parameters
    ----------
    parent : QtWidgets.QWidget
        Parent widget making the request.
    title : str
        Dialog title.
    file_filter : str
        Qt file filter string.
    folder : str
        Folder the dialog opens in.
    saving : bool, optional
        Save dialog if True, open dialog otherwise. Default is True.

    Returns
    -------
    str | None
        Selected path, or None if the user cancels the dialog.
    """
    if saving:
        dialog = QtWidgets.QFileDialog.getSaveFileName
    else:
        dialog = QtWidgets.QFileDialog.getOpenFileName
    path, _ = dialog(parent, title, folder, file_filter)
    return path if path else None
