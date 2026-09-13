"""Checkbox list widget for ``Sequence[PDevice]`` and ``Set[PDevice]`` parameters.

``DeviceSequenceEdit`` subclasses ``magicgui.widgets.bases.ValueWidget`` and is
backed by a Qt ``_CheckboxListWidget``. Its backend, ``_QCheckboxBackend``,
implements ``ValueWidgetProtocol``, so ``magicgui`` containers accept the widget
as is, without ``_explicitly_hidden`` or ``_LabeledWidget`` errors.

Every device is shown as a ``QCheckBox`` in a vertical list; a checked box is a
selected device.

``value`` is a ``list[str]`` of checked device names, in registry order;
``resolve_arguments`` turns it into a ``set`` for a ``Set[PDevice]``
annotation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from magicgui.backends._qtpy.widgets import QBaseValueWidget
from magicgui.widgets.bases import ValueWidget
from psygnal import Signal
from qtpy import QtCore
from qtpy import QtWidgets as QtW

if TYPE_CHECKING:
    from collections.abc import Callable


class _QCheckboxBackend(QBaseValueWidget):
    """Qt backend for ``DeviceSequenceEdit``.

    Wraps ``_CheckboxListWidget`` and satisfies ``ValueWidgetProtocol``, so
    ``magicgui`` containers accept it like any widget.
    """

    _qwidget: _CheckboxListWidget

    def __init__(self, parent: QtW.QWidget | None = None, **kwargs: Any) -> None:
        choices: list[str] = kwargs.pop("choices", [])
        super().__init__(
            _CheckboxListWidget,
            "get_value",
            "set_value",
            "selection_changed",
            parent=parent,
            **kwargs,
        )
        self._qwidget.set_choices(choices)

    def _mgui_bind_change_callback(self, callback: Callable[[Any], Any]) -> None:
        """Connect unconditionally.

        The inherited version first tests the signal's truth value, which works
        for a Qt signal but not a ``psygnal`` one: without connections it is
        falsy, and the callback would be dropped.
        """
        self._qwidget.selection_changed.connect(callback)

    def _mgui_set_value(self, value: Any) -> None:
        """Accept any iterable of names, and treat ``None`` as an empty selection."""
        if isinstance(value, (list, tuple, set, frozenset)):
            self._qwidget.set_value(list(value))
        elif value is None:
            self._qwidget.set_value([])

    def _mgui_get_width(self) -> int:
        """Report the preferred width: the list grows with the device pool."""
        return self._qwidget.sizeHint().width()

    def _mgui_get_height(self) -> int:
        """Report the preferred height: the list grows with the device pool."""
        return self._qwidget.sizeHint().height()


class DeviceSequenceEdit(ValueWidget[list[str]]):
    """Checkbox-list ``ValueWidget`` for ``Sequence[PDevice]`` / ``Set[PDevice]``.

    Subclasses ``magicgui.widgets.bases.ValueWidget``, so ``mgw.Container``
    accepts it like any ``magicgui`` widget.

    Parameters
    ----------
    name : str
        Widget / parameter name.
    choices : list[str]
        Every device name, in registry order.
    value : list[str], optional
        Names checked initially. None by default.
    label : str | None, optional
        Label shown in the parent container. Defaults to *name*.
    """

    def __init__(
        self,
        name: str = "",
        choices: list[str] | None = None,
        value: list[str] | None = None,
        label: str | None = None,
    ) -> None:
        super().__init__(
            widget_type=_QCheckboxBackend,
            name=name,
            label=label,
            backend_kwargs={"choices": choices or []},
        )
        if value:
            self.value = value

    def get_value(self) -> list[str]:
        """Return the checked device names in registry order."""
        return self._widget._mgui_get_value()  # type: ignore[no-any-return]

    def set_value(self, value: list[str]) -> None:
        """Check the devices named in a list, set or frozenset."""
        self._widget._mgui_set_value(value)


class _CheckboxListWidget(QtW.QWidget):
    """Vertical stack of ``QCheckBox`` widgets plus a count label.

    Choices are supplied after construction through ``set_choices``, since
    ``magicgui``'s backend base instantiates the Qt widget itself.
    """

    selection_changed = Signal(list)

    def __init__(self, parent: QtW.QWidget | None = None) -> None:
        super().__init__(parent)
        self._checkboxes: dict[str, QtW.QCheckBox] = {}

        self._layout = QtW.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)

        self._count_label = QtW.QLabel()
        self._count_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self._count_label.setStyleSheet("color: #888; font-size: 10px;")
        self._layout.addWidget(self._count_label)

        self._update_count_label()

    def set_choices(self, choices: list[str]) -> None:
        """Replace the device pool, above the count label.

        A removed checkbox is disconnected first; otherwise it would keep
        emitting selections ``get_value`` no longer reports.
        """
        for stale in self._checkboxes.values():
            stale.toggled.disconnect(self._emit)
            stale.setParent(None)
            stale.deleteLater()
        self._checkboxes.clear()
        for name in choices:
            cb = QtW.QCheckBox(name)
            cb.toggled.connect(self._emit)
            self._layout.insertWidget(self._layout.count() - 1, cb)
            self._checkboxes[name] = cb
        self._update_count_label()

    def get_value(self) -> list[str]:
        """Return names of checked devices in registry order."""
        return [name for name, cb in self._checkboxes.items() if cb.isChecked()]

    def set_value(self, names: list[str]) -> None:
        """Set checked state, suppressing intermediate signals."""
        name_set = set(names)
        for name, cb in self._checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(name in name_set)
            cb.blockSignals(False)
        self._update_count_label()
        self.selection_changed.emit(self.get_value())

    def _emit(self) -> None:
        self._update_count_label()
        self.selection_changed.emit(self.get_value())

    def _update_count_label(self) -> None:
        n = sum(cb.isChecked() for cb in self._checkboxes.values())
        total = len(self._checkboxes)
        self._count_label.setText(f"{n} / {total} selected")
