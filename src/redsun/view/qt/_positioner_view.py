"""The built-in view moving devices by hand."""

from __future__ import annotations

from collections.abc import Sequence  # noqa: TC003
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    NotRequired,
    Protocol,
    TypedDict,
    TypeGuard,
)

from psygnal import Signal
from qtpy import QtCore
from qtpy import QtWidgets as QtW
from superqt import QCollapsible, QLabeledSlider

from redsun.log import Loggable
from redsun.ports import slot
from redsun.presenter import DescribesAxes  # noqa: TC001
from redsun.qt import Dock
from redsun.view import shortcut
from redsun.view.qt.treeview import ConfigurationTab

from ..._settings import Settings  # noqa: TC001
from ._icons import set_collapsible_icons
from ._positioner_group import PositionerGroup, StepBox, tool_button

if TYPE_CHECKING:
    from collections.abc import Mapping

    from redsun.utils.devices import AxisInfo
    from redsun.view import Placement

DEFAULT_STEPS = (0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)
"""Step sizes offered in each axis' step box."""

REPEAT_INTERVAL_RANGE = (10, 300)
"""Milliseconds the repeat interval of a held step button can be set between."""

REPEAT_INTERVAL_TICK = 50
"""Milliseconds between two ticks of the repeat interval slider."""


class MakesPositionerGroup(Protocol):
    """Builds the widget of one device as `PositionerView.setup` asks for it."""

    def __call__(
        self,
        device: str,
        axes: Mapping[str, AxisInfo],
        *,
        steps: Sequence[float],
        repeat_delay: int,
        repeat_interval: int,
        step_box: StepBox,
        parent: QtW.QWidget,
    ) -> PositionerGroup: ...


class SavedPosition(TypedDict):
    """A device's positions, saved under a name."""

    name: str
    """Name shown and edited in the view."""

    device: str
    """Device the positions belong to."""

    positions: dict[str, float]
    """Position of each axis, by axis name."""

    context: NotRequired[dict[str, float]]
    """Configuration values in the units of an axis' position, when saved."""


def is_saved_position(item: object) -> TypeGuard[dict[str, Any]]:
    """Tell whether *item* is a well-formed saved position."""
    return (
        isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and isinstance(item.get("device"), str)
        and isinstance(item.get("positions"), dict)
        and all(
            isinstance(axis, str)
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            for axis, value in item["positions"].items()
        )
    )


def numbers(values: object) -> dict[str, float]:
    """Return the entries of *values* that are numbers, by key."""
    if not isinstance(values, dict):
        return {}
    return {
        key: float(value)
        for key, value in values.items()
        if isinstance(key, str)
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    }


def saved_positions(stored: object) -> tuple[list[SavedPosition], int]:
    """Return the well-formed entries in *stored*, and how many were not."""
    items = stored if isinstance(stored, list) else []
    entries: list[SavedPosition] = []
    for item in items:
        if not is_saved_position(item):
            continue
        entry = SavedPosition(
            name=item["name"],
            device=item["device"],
            positions=numbers(item["positions"]),
        )
        if "context" in item:
            entry["context"] = numbers(item["context"])
        entries.append(entry)
    return entries, len(items) - len(entries)


class GroupScrollArea(QtW.QScrollArea):
    """A scroll area asking for the width its content needs to be shown whole."""

    def sizeHint(self) -> QtCore.QSize:
        """Ask for the content's minimum width, beside the vertical scroll bar."""
        hint = super().sizeHint()
        content, bar = self.widget(), self.verticalScrollBar()
        if content is None or bar is None:
            return hint
        # the base class remembers the content's size from when it was set,
        # before the groups were added
        width = (
            content.minimumSizeHint().width()
            + bar.sizeHint().width()
            + 2 * self.frameWidth()
        )
        return QtCore.QSize(max(hint.width(), width), hint.height())


class PositionerView(QtW.QWidget, Loggable):
    """Move devices by hand: a row per axis, grouped by device.

    The Motors tab holds one [`PositionerGroup`][redsun.view.qt.builtins.PositionerGroup]
    per device the positioner describes, and the saved positions. The
    Configuration tab shows and edits the configuration of every axis. The
    Advanced tab sets the repeat interval of held step buttons. With an axis
    row or its step button focused, Left and Right step that axis down and
    up; they are keyboard shortcuts, so the session file and the Keyboard
    shortcuts list show and change them. The session's
    settings keep the saved positions and the repeat interval, under keys
    named after this view.

    Parameters
    ----------
    repeat_delay
        Milliseconds a step button is held before its step repeats.
    repeat_interval
        Milliseconds between two repeated steps, until one is set in the
        Advanced tab; kept between 10 and 300.
    steps
        Step sizes offered in each axis' step box.
    step_box
        `"combobox"` lists the sizes in *steps*; `"spinbox"` takes any size
        from the smallest to the largest of them, starting from the default
        one, and its arrows move it by decades.
    undo_delay
        Milliseconds Undo is offered after a saved position is removed.
    """

    placement: Placement = Dock("right")
    """Where the view sits in the main window."""

    group_class: ClassVar[MakesPositionerGroup] = PositionerGroup
    """Widget built for each device; a subclass may name a subclass of its own that takes the same arguments."""

    sig_move = Signal(str, str, float)
    """Device, axis and step, when a step button is pressed or repeats, or Left or Right steps the focused axis."""

    sig_move_to = Signal(str, dict)
    """Device and the positions to go to, by axis."""

    sig_stop_device = Signal(str)
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
        step_box: StepBox = "combobox",
        undo_delay: int = 5000,
    ) -> None:
        super().__init__(parent)
        self.name = name
        self._repeat_delay = repeat_delay
        self._step_box: StepBox = step_box
        self._steps = tuple(steps)
        self._groups: dict[str, PositionerGroup] = {}
        self._locked: frozenset[str] = frozenset()
        self._settings: Settings | None = None
        self._configuration_tab: ConfigurationTab | None = None
        self._configuration = QtW.QVBoxLayout()
        self._entries: list[SavedPosition] = []
        self._entry_buttons: list[tuple[str, QtW.QToolButton]] = []
        self._values: dict[str, object] = {}
        self._context_keys: dict[str, list[str]] = {}
        self._confirming: SavedPosition | None = None
        self._removed: tuple[int, SavedPosition] | None = None

        self._interval = QLabeledSlider(QtCore.Qt.Orientation.Horizontal, self)
        self._interval.setRange(*REPEAT_INTERVAL_RANGE)
        self._interval.setTickPosition(QtW.QSlider.TickPosition.TicksBelow)
        self._interval.setTickInterval(REPEAT_INTERVAL_TICK)
        self._interval.setValue(repeat_interval)

        self._devices = QtW.QVBoxLayout()
        self._saved = QCollapsible("Saved positions", self)
        set_collapsible_icons(self._saved)
        self._undo_row = QtW.QWidget(self)
        self._undo_label = QtW.QLabel(self._undo_row)
        self._undo_label.setWordWrap(True)
        undo = tool_button("undo", "Undo the removal", self._undo_row)
        undo.setObjectName("saved-undo")
        undo.clicked.connect(self._undo)
        undo_layout = QtW.QHBoxLayout(self._undo_row)
        undo_layout.setContentsMargins(0, 0, 0, 0)
        undo_layout.addWidget(self._undo_label, 1)
        undo_layout.addWidget(undo)
        self._undo_row.hide()
        self._undo_timer = QtCore.QTimer(self)
        self._undo_timer.setSingleShot(True)
        self._undo_timer.setInterval(undo_delay)
        self._undo_timer.timeout.connect(self._undo_row.hide)
        self._entry_list = QtW.QWidget(self)
        self._entry_layout = QtW.QVBoxLayout(self._entry_list)
        self._saved.addWidget(self._undo_row)
        self._saved.addWidget(self._entry_list)
        motors = QtW.QWidget(self)
        motors_layout = QtW.QVBoxLayout(motors)
        motors_layout.addLayout(self._devices)
        motors_layout.addWidget(self._saved)
        motors_layout.addStretch(1)
        self._scroll = GroupScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(motors)

        advanced = QtW.QWidget(self)
        form = QtW.QFormLayout(advanced)
        form.setRowWrapPolicy(QtW.QFormLayout.RowWrapPolicy.WrapAllRows)
        form.addRow("Repeat interval (ms)", self._interval)

        configuration = QtW.QWidget(self)
        configuration.setLayout(self._configuration)

        self._tabs = QtW.QTabWidget(self)
        self._tabs.addTab(self._scroll, "Motors")
        self._tabs.addTab(configuration, "Configuration")
        self._tabs.addTab(advanced, "Advanced")
        QtW.QVBoxLayout(self).addWidget(self._tabs)

    @property
    def tabs(self) -> QtW.QTabWidget:
        """The Motors, Configuration and Advanced tabs, to which a subclass may add."""
        return self._tabs

    def setup(self, positioner: DescribesAxes, settings: Settings) -> None:
        """Build a group per device *positioner* describes, and read *settings*."""
        self._settings = settings
        stored = settings.get(self._key("repeat_interval"))
        if isinstance(stored, int) and not isinstance(stored, bool):
            self._interval.setValue(stored)
        for device, axes in positioner.axes.items():
            group = self.group_class(
                device,
                axes,
                steps=self._steps,
                repeat_delay=self._repeat_delay,
                repeat_interval=self._interval.value(),
                step_box=self._step_box,
                parent=self,
            )
            group.sig_move.connect(self.sig_move.emit)
            group.sig_move_to.connect(self.sig_move_to.emit)
            group.sig_stop.connect(self.sig_stop_device.emit)
            self._groups[device] = group
            self._devices.addWidget(group)
        self._interval.valueChanged.connect(self._set_repeat_interval)
        self._interval.sliderReleased.connect(self._store_repeat_interval)
        descriptors = positioner.configuration.descriptors
        readings = positioner.configuration.readings
        self._values = {key: reading["value"] for key, reading in readings.items()}
        # an offset or a resolution in position units changes where a saved
        # position puts the axis
        self._context_keys = {
            device: [
                key
                for info in axes.values()
                if info.readback.units is not None
                for key in info.configuration
                if key in descriptors
                and descriptors[key].get("units") == info.readback.units
            ]
            for device, axes in positioner.axes.items()
        }
        self._configuration_tab = ConfigurationTab(positioner.configuration, self)
        self._configuration_tab.sig_configure.connect(self.sig_configure.emit)
        self._configuration.addWidget(self._configuration_tab)
        for group in self._groups.values():
            group.sig_save.connect(self._save)
        stored_positions = settings.get(self._key("saved_positions"), [])
        if not isinstance(stored_positions, list):
            self.logger.warning(
                "Ignoring saved positions that are not a list; the next save replaces them"
            )
        self._entries, skipped = saved_positions(stored_positions)
        if skipped:
            self.logger.warning(
                f"Skipping {skipped} saved positions that are not well formed"
            )
        self._show_entries()
        # the window sizes the view from hints it kept from before the groups
        self._scroll.updateGeometry()

    @slot(signal="sig_readback")
    def update_readback(self, device: str, axis: str, value: float) -> None:
        """Show *value* as the readback of *axis* of *device*."""
        self._groups[device].set_readback(axis, value)

    @slot(signal="sig_limits")
    def update_limits(
        self, device: str, axis: str, low: float | None, high: float | None
    ) -> None:
        """Take targets for *axis* of *device* from *low* to *high* only."""
        self._groups[device].set_limits(axis, low, high)

    @slot(signal="sig_moving")
    def set_moving(self, device: str, moving: bool) -> None:
        """Show whether *device* moves."""
        self._groups[device].set_moving(moving)

    @slot(signal="sig_failed")
    def set_failed(self, device: str, message: str) -> None:
        """Show that the last move of *device* failed with *message*."""
        self._groups[device].set_failed(message)

    @slot(signal="sig_configuration")
    def update_configuration(self, key: str, value: object) -> None:
        """Show *value*, read back from the configuration signal *key*."""
        self._values[key] = value
        if self._configuration_tab is not None:
            self._configuration_tab.update_value(key, value)

    @slot(signal="sig_locks_changed")
    def set_locked(self, names: frozenset[str]) -> None:
        """Disable the controls of the devices in *names*, and enable the rest."""
        self._locked = names
        for device, group in self._groups.items():
            group.set_locked(device in names)
        if self._configuration_tab is not None:
            self._configuration_tab.set_locked(names)
        self._lock_entries()

    def _row_has_focus(self) -> bool:
        return any(group.focused_axis() is not None for group in self._groups.values())

    @shortcut(
        "Left", title="Step the focused axis down", scope="view", when=_row_has_focus
    )
    def step_down(self) -> None:
        """Step the axis whose row has focus down by its step size."""
        self._step_focused(-1.0)

    @shortcut(
        "Right", title="Step the focused axis up", scope="view", when=_row_has_focus
    )
    def step_up(self) -> None:
        """Step the axis whose row has focus up by its step size."""
        self._step_focused(1.0)

    def _step_focused(self, sign: float) -> None:
        for group in self._groups.values():
            if (axis := group.focused_axis()) is not None:
                group.step(axis, sign)

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
                positions=self._groups[device].positions,
                context=numbers(
                    {key: self._values.get(key) for key in self._context_keys[device]}
                ),
            )
        )
        self._store()
        self._saved.expand()

    def _rename(self, entry: SavedPosition, name: str) -> None:
        if name == entry["name"]:
            return
        entry["name"] = name
        self._write()

    def _remove(self, entry: SavedPosition) -> None:
        self._removed = (self._entries.index(entry), entry)
        self._entries.remove(entry)
        self._store()
        self._undo_label.setText(f"Removed {entry['name']}")
        self._undo_row.show()
        self._undo_timer.start()

    def _undo(self) -> None:
        self._undo_timer.stop()
        self._undo_row.hide()
        if self._removed is not None:
            index, entry = self._removed
            self._removed = None
            self._entries.insert(index, entry)
            self._store()

    def _go(self, entry: SavedPosition) -> None:
        axes = self._groups[entry["device"]].positions
        positions = {a: v for a, v in entry["positions"].items() if a in axes}
        missing = sorted(set(entry["positions"]) - set(positions))
        if missing:
            self.logger.warning(
                f"{entry['name']}: {entry['device']} has no axis {', '.join(missing)}"
            )
        if not positions:
            return
        changed = [
            key
            for key, value in entry.get("context", {}).items()
            if self._values.get(key, value) != value
        ]
        if changed and self._confirming is not entry:
            self._confirming = entry
            self._groups[entry["device"]].show_message(
                f"{entry['name']}: {', '.join(changed)} changed since it was saved;"
                " Go again to move"
            )
            return
        self._confirming = None
        self.sig_move_to.emit(entry["device"], positions)

    def _store(self) -> None:
        self._write()
        self._show_entries()

    def _write(self) -> None:
        if self._settings is not None:
            self._settings.set(
                self._key("saved_positions"),
                [
                    {
                        "name": entry["name"],
                        "device": entry["device"],
                        "positions": dict(entry["positions"].items()),
                        **(
                            {"context": dict(entry["context"].items())}
                            if "context" in entry
                            else {}
                        ),
                    }
                    for entry in self._entries
                ],
            )

    def _show_entries(self) -> None:
        while (item := self._entry_layout.takeAt(0)) is not None:
            if (widget := item.widget()) is not None:
                widget.setParent(None)
                widget.deleteLater()
        shown = [entry for entry in self._entries if entry["device"] in self._groups]
        self._entry_buttons = []
        for index, entry in enumerate(shown):
            row, go = self._entry_row(index, entry)
            self._entry_layout.addWidget(row)
            self._entry_buttons.append((entry["device"], go))
        self._lock_entries()

    def _entry_row(
        self, index: int, entry: SavedPosition
    ) -> tuple[QtW.QWidget, QtW.QToolButton]:
        row = QtW.QWidget(self._entry_list)
        name = QtW.QLineEdit(entry["name"], row)
        name.setObjectName(f"saved:{index}")
        name.setAccessibleName("Saved position name")
        name.editingFinished.connect(lambda: self._rename(entry, name.text()))
        summary = "  ".join(f"{a} {v:g}" for a, v in entry["positions"].items())
        go = tool_button("crosshairs-gps", f"Go to {entry['name']}", row)
        go.setObjectName(f"saved-go:{index}")
        go.setToolTip(f"Move {entry['device']} to {summary}")
        go.clicked.connect(lambda: self._go(entry))
        remove = tool_button("close", f"Remove {entry['name']}", row)
        remove.setObjectName(f"saved-remove:{index}")
        remove.clicked.connect(lambda: self._remove(entry))
        details = QtW.QLabel(f"{entry['device']}  {summary}", row)
        details.setWordWrap(True)
        layout = QtW.QGridLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(name, 0, 0)
        layout.addWidget(go, 0, 1)
        layout.addWidget(remove, 0, 2)
        layout.addWidget(details, 1, 0, 1, 3)
        layout.setColumnStretch(0, 1)
        return row, go

    def _lock_entries(self) -> None:
        for device, button in self._entry_buttons:
            button.setEnabled(device not in self._locked)

    def _set_repeat_interval(self, milliseconds: int) -> None:
        for group in self._groups.values():
            group.set_repeat_interval(milliseconds)
        # dragging the slider would write the settings file at every tick
        if not self._interval.isSliderDown():
            self._store_repeat_interval()

    def _store_repeat_interval(self) -> None:
        if self._settings is not None:
            self._settings.set(self._key("repeat_interval"), self._interval.value())
