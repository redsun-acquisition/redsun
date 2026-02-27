"""Checkbox-list widget for ``Sequence[PDevice]`` and ``Set[PDevice]`` parameters.

``DeviceSequenceEdit`` is a proper ``magicgui.widgets.bases.ValueWidget`` subclass,
backed by a Qt ``_CheckboxListWidget``.  The backend class (``_QCheckboxBackend``)
implements ``ValueWidgetProtocol`` so that the widget passes through the magicgui
container machinery unchanged — no ``_explicitly_hidden`` or ``_LabeledWidget``
errors.

The full device pool is always visible as a vertical list of ``QCheckBox`` widgets.
Checked = selected, unchecked = not.

``value`` returns ``list[str]`` (names of checked devices, in registry order).
``resolve_arguments`` is responsible for the final coercion to ``set`` when the
annotation is ``Set[PDevice]``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from magicgui.backends._qtpy.widgets import EventFilter
from magicgui.widgets import protocols
from magicgui.widgets.bases import ValueWidget
from psygnal import Signal
from qtpy import QtCore
from qtpy import QtWidgets as QtW

if TYPE_CHECKING:
    from collections.abc import Callable


# ---------------------------------------------------------------------------
# Qt backend — implements ValueWidgetProtocol around _CheckboxListWidget
# ---------------------------------------------------------------------------


class _QCheckboxBackend(protocols.ValueWidgetProtocol):
    """Qt backend for ``DeviceSequenceEdit``.

    Wraps ``_CheckboxListWidget`` and satisfies ``ValueWidgetProtocol`` so
    magicgui's container machinery accepts it as a first-class widget.
    """

    def __init__(self, parent: QtW.QWidget | None = None, **kwargs: Any) -> None:
        choices: list[str] = kwargs.pop("choices", [])
        self._qwidget = _CheckboxListWidget(choices=choices)
        if parent is not None:
            self._qwidget.setParent(parent)
        self._event_filter = EventFilter()
        self._qwidget.installEventFilter(self._event_filter)
        self._change_callback: Callable[[Any], Any] | None = None
        self._qwidget.selection_changed.connect(self._on_change)

    # ------------------------------------------------------------------
    # ValueWidgetProtocol
    # ------------------------------------------------------------------

    def _mgui_get_value(self) -> list[str]:
        return self._qwidget.get_value()

    def _mgui_set_value(self, value: Any) -> None:
        if isinstance(value, (list, tuple, set, frozenset)):
            self._qwidget.set_value(list(value))
        elif value is None:
            self._qwidget.set_value([])

    def _mgui_bind_change_callback(self, callback: Callable[[Any], Any]) -> None:
        self._change_callback = callback

    def _on_change(self, value: list[str]) -> None:
        if self._change_callback is not None:
            self._change_callback(value)

    # ------------------------------------------------------------------
    # WidgetProtocol
    # ------------------------------------------------------------------

    def _mgui_close_widget(self) -> None:
        self._qwidget.close()

    def _mgui_get_visible(self) -> bool:
        return self._qwidget.isVisible()

    def _mgui_set_visible(self, value: bool) -> None:
        self._qwidget.setVisible(value)

    def _mgui_get_enabled(self) -> bool:
        return self._qwidget.isEnabled()

    def _mgui_set_enabled(self, enabled: bool) -> None:
        self._qwidget.setEnabled(enabled)

    def _mgui_get_parent(self) -> Any:
        return self._qwidget.parent()

    def _mgui_set_parent(self, widget: Any) -> None:
        native = widget.native if hasattr(widget, "native") else widget
        self._qwidget.setParent(native)

    def _mgui_get_native_widget(self) -> QtW.QWidget:
        return self._qwidget

    def _mgui_get_root_native_widget(self) -> QtW.QWidget:
        return self._qwidget

    def _mgui_get_width(self) -> int:
        return self._qwidget.sizeHint().width()

    def _mgui_set_width(self, value: int) -> None:
        self._qwidget.resize(int(value), self._qwidget.height())

    def _mgui_get_min_width(self) -> int:
        return self._qwidget.minimumWidth()

    def _mgui_set_min_width(self, value: int) -> None:
        self._qwidget.setMinimumWidth(int(value))

    def _mgui_get_max_width(self) -> int:
        return self._qwidget.maximumWidth()

    def _mgui_set_max_width(self, value: int) -> None:
        self._qwidget.setMaximumWidth(int(value))

    def _mgui_get_height(self) -> int:
        return self._qwidget.sizeHint().height()

    def _mgui_set_height(self, value: int) -> None:
        self._qwidget.resize(self._qwidget.width(), int(value))

    def _mgui_get_min_height(self) -> int:
        return self._qwidget.minimumHeight()

    def _mgui_set_min_height(self, value: int) -> None:
        self._qwidget.setMinimumHeight(int(value))

    def _mgui_get_max_height(self) -> int:
        return self._qwidget.maximumHeight()

    def _mgui_set_max_height(self, value: int) -> None:
        self._qwidget.setMaximumHeight(int(value))

    def _mgui_get_tooltip(self) -> str:
        return self._qwidget.toolTip()

    def _mgui_set_tooltip(self, value: str | None) -> None:
        self._qwidget.setToolTip(str(value) if value else "")

    def _mgui_bind_parent_change_callback(self, callback: Callable[..., Any]) -> None:
        self._event_filter.parentChanged.connect(callback)

    def _mgui_render(self) -> None:  # type: ignore[override]  # pragma: no cover
        raise NotImplementedError("render() is not supported for DeviceSequenceEdit")


# ---------------------------------------------------------------------------
# Public magicgui widget
# ---------------------------------------------------------------------------


class DeviceSequenceEdit(ValueWidget[list[str]]):
    """Checkbox-list ``ValueWidget`` for ``Sequence[PDevice]`` / ``Set[PDevice]``.

    Inherits from ``magicgui.widgets.bases.ValueWidget`` so it is accepted
    transparently by ``mgw.Container`` and the rest of the magicgui machinery.

    Layout::

        ☑ mmcore
        ☐ camera2
        ☑ camera3
                    2 / 3 selected

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

    _widget: _QCheckboxBackend

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
        return self._widget._mgui_get_value()

    def set_value(self, value: list[str]) -> None:
        """Set checked devices from a list (or set/frozenset) of names."""
        self._widget._mgui_set_value(value)


# ---------------------------------------------------------------------------
# Pure-Qt implementation
# ---------------------------------------------------------------------------


class _CheckboxListWidget(QtW.QWidget):
    """Vertical stack of ``QCheckBox`` widgets plus a count label.

    Parameters
    ----------
    choices : list[str]
        Ordered list of device names.
    """

    selection_changed = Signal(list)

    def __init__(
        self,
        choices: list[str],
        parent: QtW.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._checkboxes: dict[str, QtW.QCheckBox] = {}

        layout = QtW.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        for name in choices:
            cb = QtW.QCheckBox(name)
            cb.toggled.connect(self._emit)
            layout.addWidget(cb)
            self._checkboxes[name] = cb

        self._count_label = QtW.QLabel()
        self._count_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self._count_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self._count_label)

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
