"""The built-in view moving devices by hand."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from psygnal import Signal
from qtpy import QtCore
from qtpy import QtWidgets as QtW
from superqt import QCollapsible, QLabeledSlider

from redsun.log import Loggable
from redsun.ports import slot
from redsun.qt import Dock

from ._positioner_group import PositionerGroup
from .treeview import DescriptorTreeView

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    from redsun import Settings
    from redsun.presenter import DescribesAxes
    from redsun.view import Placement

DEFAULT_STEPS = (0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)
"""Step sizes offered in each axis' step box."""

REPEAT_INTERVAL_RANGE = (10, 300)
"""Milliseconds the repeat interval of a held step button can be set between."""

REPEAT_INTERVAL_TICK = 50
"""Milliseconds between two ticks of the repeat interval slider."""


class SavedPosition(TypedDict):
    """A device's positions, saved under a name."""

    name: str
    """Name shown and edited in the view."""

    device: str
    """Device the positions belong to."""

    positions: dict[str, float]
    """Position of each axis, by axis name."""


def saved_positions(stored: object) -> tuple[list[SavedPosition], int]:
    """Return the well-formed entries in *stored*, and how many were not."""
    entries: list[SavedPosition] = []
    items = stored if isinstance(stored, list) else []
    for item in items:
        if (
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("device"), str)
            and isinstance(item.get("positions"), dict)
            and all(
                isinstance(axis, str) and isinstance(value, (int, float))
                for axis, value in item["positions"].items()
            )
        ):
            entries.append(
                SavedPosition(
                    name=item["name"],
                    device=item["device"],
                    positions={a: float(v) for a, v in item["positions"].items()},
                )
            )
    return entries, len(items) - len(entries)


class PositionerView(QtW.QWidget, Loggable):
    """Move devices by hand: a row per axis, grouped by device.

    The Motors tab holds one [`PositionerGroup`][redsun.view.qt.builtins.PositionerGroup]
    per device the positioner describes, and the saved positions. The
    Advanced tab sets the repeat interval of held step buttons, which the
    session's settings keep.

    Parameters
    ----------
    repeat_delay
        Milliseconds a step button is held before its step repeats.
    repeat_interval
        Milliseconds between two repeated steps, until one is set in the
        Advanced tab; kept between 10 and 300.
    steps
        Step sizes offered in each axis' step box.
    """

    placement: Placement = Dock("right")

    sig_move = Signal(str, str, float)
    """Device, axis and step, when a step button is pressed or repeats."""

    sig_move_to = Signal(str, dict)
    """Device and the positions to go to, by axis."""

    sig_stop = Signal(str)
    """Device, when its Stop button is clicked."""

    sig_configure = Signal(str, object)
    """Key and value of an edit in the Configuration tab."""

    def __init__(
        self,
        name: str,
        parent: QtW.QWidget,
        *,
        repeat_delay: int = 400,
        repeat_interval: int = 50,
        steps: Sequence[float] = DEFAULT_STEPS,
    ) -> None:
        super().__init__(parent)
        self.name = name
        self._repeat_delay = repeat_delay
        self._steps = tuple(steps)
        self._groups: dict[str, PositionerGroup] = {}
        self._locked: frozenset[str] = frozenset()
        self._settings: Settings | None = None
        self._tree: DescriptorTreeView | None = None
        self._configuration = QtW.QVBoxLayout()
        self._entries: list[SavedPosition] = []
        self._entry_buttons: dict[str, list[QtW.QPushButton]] = {}

        self._interval = QLabeledSlider(QtCore.Qt.Orientation.Horizontal, self)
        self._interval.setRange(*REPEAT_INTERVAL_RANGE)
        self._interval.setTickPosition(QtW.QSlider.TickPosition.TicksBelow)
        self._interval.setTickInterval(REPEAT_INTERVAL_TICK)
        self._interval.setValue(repeat_interval)

        self._devices = QtW.QVBoxLayout()
        self._saved = QCollapsible("Saved positions", self)
        self._entry_list = QtW.QWidget(self)
        self._entry_layout = QtW.QVBoxLayout(self._entry_list)
        self._saved.addWidget(self._entry_list)
        motors = QtW.QWidget(self)
        motors_layout = QtW.QVBoxLayout(motors)
        motors_layout.addLayout(self._devices)
        motors_layout.addWidget(self._saved)
        motors_layout.addStretch(1)
        scroll = QtW.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(motors)

        advanced = QtW.QWidget(self)
        form = QtW.QFormLayout(advanced)
        form.addRow("Repeat interval (ms)", self._interval)

        configuration = QtW.QWidget(self)
        configuration.setLayout(self._configuration)

        tabs = QtW.QTabWidget(self)
        tabs.addTab(scroll, "Motors")
        tabs.addTab(configuration, "Configuration")
        tabs.addTab(advanced, "Advanced")
        QtW.QVBoxLayout(self).addWidget(tabs)

    def setup(self, positioner: DescribesAxes, settings: Settings) -> None:
        """Build a group per device *positioner* describes, and read *settings*."""
        self._settings = settings
        stored = settings.get(self._key("repeat_interval"))
        if isinstance(stored, int):
            self._interval.setValue(stored)
        for device, axes in positioner.axes().items():
            group = PositionerGroup(
                device,
                axes,
                steps=self._steps,
                repeat_delay=self._repeat_delay,
                repeat_interval=self._interval.value(),
                parent=self,
            )
            group.sig_move.connect(self.sig_move.emit)
            group.sig_move_to.connect(self.sig_move_to.emit)
            group.sig_stop.connect(self.sig_stop.emit)
            self._groups[device] = group
            self._devices.addWidget(group)
        self._interval.valueChanged.connect(self._set_repeat_interval)
        descriptors, readings = positioner.configuration()
        if descriptors:
            self._tree = DescriptorTreeView(descriptors, readings, self)
            self._tree.sig_property_changed.connect(self._configure)
            self._configuration.addWidget(self._tree)
        else:
            self._configuration.addWidget(
                QtW.QLabel("No axis has a configuration.", self)
            )
        for group in self._groups.values():
            group.sig_save.connect(self._save)
        self._entries, skipped = saved_positions(
            settings.get(self._key("saved_positions"), [])
        )
        if skipped:
            self.logger.warning(
                f"Skipping {skipped} saved positions that are not well formed"
            )
        self._show_entries()

    @slot
    def update_readback(self, device: str, axis: str, value: float) -> None:
        """Show *value* as the readback of *axis* of *device*."""
        self._groups[device].set_readback(axis, value)

    @slot
    def set_moving(self, device: str, moving: bool) -> None:
        """Show whether *device* moves."""
        self._groups[device].set_moving(moving)

    @slot
    def set_failed(self, device: str, message: str) -> None:
        """Show that the last move of *device* failed with *message*."""
        self._groups[device].set_failed(message)

    @slot
    def update_configuration(self, key: str, value: Any) -> None:
        """Show *value*, read back from the configuration signal *key*."""
        if self._tree is not None:
            self._tree.set_value(key, value)

    @slot
    def set_locked(self, names: frozenset[str]) -> None:
        """Disable the controls of the devices in *names*, and enable the rest."""
        self._locked = names
        for device, group in self._groups.items():
            group.set_locked(device in names)
        self._lock_entries()

    def _key(self, setting: str) -> str:
        return f"{self.name}.{setting}"

    def _save(self, device: str) -> None:
        taken = {entry["name"] for entry in self._entries}
        number = 1
        while f"{device} {number}" in taken:
            number += 1
        self._entries.append(
            SavedPosition(
                name=f"{device} {number}",
                device=device,
                positions=self._groups[device].positions(),
            )
        )
        self._store()

    def _rename(self, entry: SavedPosition, name: str) -> None:
        entry["name"] = name
        self._store()

    def _remove(self, entry: SavedPosition) -> None:
        self._entries.remove(entry)
        self._store()

    def _go(self, entry: SavedPosition) -> None:
        axes = self._groups[entry["device"]].positions()
        positions = {a: v for a, v in entry["positions"].items() if a in axes}
        self.sig_move_to.emit(entry["device"], positions)

    def _store(self) -> None:
        if self._settings is not None:
            self._settings.set(
                self._key("saved_positions"),
                [
                    {
                        "name": entry["name"],
                        "device": entry["device"],
                        "positions": dict(entry["positions"].items()),
                    }
                    for entry in self._entries
                ],
            )
        self._show_entries()

    def _show_entries(self) -> None:
        while (item := self._entry_layout.takeAt(0)) is not None:
            if (widget := item.widget()) is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._entry_buttons = {}
        shown = [entry for entry in self._entries if entry["device"] in self._groups]
        for index, entry in enumerate(shown):
            row = QtW.QWidget(self._entry_list)
            name = QtW.QLineEdit(entry["name"], row)
            name.setObjectName(f"saved:{index}")
            name.editingFinished.connect(
                lambda e=entry, n=name: self._rename(e, n.text())
            )
            summary = "  ".join(f"{a} {v:g}" for a, v in entry["positions"].items())
            go = QtW.QPushButton("Go", row)
            go.setObjectName(f"saved-go:{index}")
            go.clicked.connect(lambda _=False, e=entry: self._go(e))
            remove = QtW.QPushButton("x", row)
            remove.setObjectName(f"saved-remove:{index}")
            remove.setToolTip("Remove this saved position")
            remove.clicked.connect(lambda _=False, e=entry: self._remove(e))
            layout = QtW.QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(name)
            layout.addWidget(QtW.QLabel(f"{entry['device']}  {summary}", row))
            layout.addWidget(go)
            layout.addWidget(remove)
            self._entry_layout.addWidget(row)
            self._entry_buttons.setdefault(entry["device"], []).append(go)
        self._lock_entries()

    def _lock_entries(self) -> None:
        for device, buttons in self._entry_buttons.items():
            for button in buttons:
                button.setEnabled(device not in self._locked)

    def _configure(self, owner: str, prop: str, value: Any) -> None:
        self.sig_configure.emit(f"{owner}-{prop}" if owner else prop, value)

    def _set_repeat_interval(self, milliseconds: int) -> None:
        for group in self._groups.values():
            group.set_repeat_interval(milliseconds)
        if self._settings is not None:
            self._settings.set(self._key("repeat_interval"), milliseconds)
