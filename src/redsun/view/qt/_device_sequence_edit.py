"""Checkbox-list widget for ``Sequence[PDevice]`` and ``Set[PDevice]`` parameters.

``DeviceSequenceEdit`` is a proper ``magicgui.widgets.bases.ValueWidget`` subclass,
backed by a Qt ``_CheckboxListWidget``.  The backend class (``_QCheckboxBackend``)
implements ``ValueWidgetProtocol`` so that the widget passes through the magicgui
container machinery unchanged - no ``_explicitly_hidden`` or ``_LabeledWidget``
errors.

The full device pool is always visible as a vertical list of ``QCheckBox`` widgets.
Checked = selected, unchecked = not.

``value`` returns ``list[str]`` (names of checked devices, in registry order).
``resolve_arguments`` is responsible for the final coercion to ``set`` when the
annotation is ``Set[PDevice]``.
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

    Wraps ``_CheckboxListWidget`` and satisfies ``ValueWidgetProtocol`` so
    magicgui's container machinery accepts it as a first-class widget.
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

        The inherited version tests the signal for truthiness first, which
        holds for a Qt signal but not for a psygnal one: with no connections
        yet it is falsy, and the callback would be dropped.
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

    Inherits from ``magicgui.widgets.bases.ValueWidget`` so it is accepted
    transparently by ``mgw.Container`` and the rest of the magicgui machinery.

    Parameters
    ----------
    name : str
        Widget / parameter name.
    choices : list[str]
        Full pool of device names (registry order).
    value : list[str], optional
        Names to pre-check.  Defaults to all unchecked.
    label : str | None, optional
        Human-readable label shown in the parent container.  Defaults to *name*.
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
        """Return names of currently checked devices in registry order."""
        return self._widget._mgui_get_value()  # type: ignore[no-any-return]

    def set_value(self, value: list[str]) -> None:
        """Set checked devices from a list (or set/frozenset) of names."""
        self._widget._mgui_set_value(value)


class _CheckboxListWidget(QtW.QWidget):
    """Vertical stack of ``QCheckBox`` widgets plus a count label.

    Choices are supplied after construction through ``set_choices``, since
    magicgui's backend base instantiates the Qt widget itself.
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

        An outgoing checkbox is disconnected before it is dropped: left
        connected it would keep emitting selections that ``get_value`` no
        longer reports.
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
