"""Checkbox-list widget for ``Sequence[PDevice]`` and ``Set[PDevice]`` parameters.

``DeviceSequenceEdit`` replaces the raw ``Select(allow_multiple=True)`` rendering
with a vertical list of ``QCheckBox`` widgets — one per available device.
Checked = selected, unchecked = not.  The full device pool is always visible,
making the selection state immediately legible without any secondary combo or
add/remove affordance.

``value`` returns ``list[str]`` (names of checked devices, in registry order),
which is exactly what the existing ``resolve_arguments`` machinery consumes.
``resolve_arguments`` is responsible for the final coercion to ``set`` when the
annotation is ``Set[PDevice]``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from psygnal import Signal
from qtpy import QtCore
from qtpy import QtWidgets as QtW

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


class DeviceSequenceEdit:
    """Checkbox-list widget for ``Sequence[PDevice]`` / ``Set[PDevice]`` parameters.

    Renders as a compact vertical list of ``QCheckBox`` widgets — one per
    device in *choices* — plus a right-aligned count label.

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
        Human-readable label for the parent form row.  Defaults to *name*.
    """

    # psygnal signal — consumed by the magicgui container machinery
    changed: Signal = Signal(object)

    def __init__(
        self,
        name: str,
        choices: list[str],
        value: list[str] | None = None,
        label: str | None = None,
    ) -> None:
        self._name = name
        self._label = label or name
        self._choices = list(choices)

        self._native = _CheckboxListWidget(
            choices=self._choices,
            on_changed=self._on_native_changed,
        )

        if value:
            self._native.set_value(value)

    # ------------------------------------------------------------------
    # magicgui ValueWidget protocol (minimal subset used by the framework)
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def label(self) -> str:
        return self._label

    @property
    def native(self) -> QtW.QWidget:
        """The underlying Qt widget."""
        return self._native

    @property
    def value(self) -> list[str]:
        """Names of currently checked devices, in registry order."""
        return self._native.get_value()

    @value.setter
    def value(self, v: list[str]) -> None:
        self._native.set_value(v)

    def get_value(self) -> list[str]:  # magicgui compat alias
        return self.value

    # ------------------------------------------------------------------
    # Make DeviceSequenceEdit iterable so PlanWidget.parameters works:
    #   {w.name: w.value for w in container}
    # ------------------------------------------------------------------

    def __iter__(self) -> Iterator[DeviceSequenceEdit]:
        yield self

    def __len__(self) -> int:
        return 1

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_native_changed(self, new_value: list[str]) -> None:
        self.changed.emit(new_value)


class _CheckboxListWidget(QtW.QWidget):
    """Vertical stack of QCheckBoxes, one per device, plus a count label.

    Parameters
    ----------
    choices : list[str]
        Ordered list of device names.
    on_changed : Callable[[list[str]], None]
        Called whenever any checkbox state changes.
    """

    def __init__(
        self,
        choices: list[str],
        on_changed: Callable[[list[str]], None],
        parent: QtW.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._choices = choices
        self._on_changed = on_changed
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
        """Set checked state from *names*, suppressing intermediate signals."""
        name_set = set(names)
        for name, cb in self._checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(name in name_set)
            cb.blockSignals(False)
        self._update_count_label()
        self._on_changed(self.get_value())

    def _emit(self) -> None:
        self._update_count_label()
        self._on_changed(self.get_value())

    def _update_count_label(self) -> None:
        n = sum(cb.isChecked() for cb in self._checkboxes.values())
        total = len(self._checkboxes)
        self._count_label.setText(f"{n} / {total} selected")
