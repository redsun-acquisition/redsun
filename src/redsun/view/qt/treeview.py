"""Tree view showing and editing device settings from their descriptors.

`DescriptorTreeView`, a `QTreeWidget`, shows `bluesky` `describe()` /
`read()` dicts as a two-column property tree.

The design follows the `ParameterTree` widget of
[pyqtgraph](https://github.com/pyqtgraph/pyqtgraph) (MIT licence,
(c) 2012 University of North Carolina at Chapel Hill, Luke Campagnola).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, assert_never

import numpy as np
from psygnal import Signal
from qtpy import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from bluesky.protocols import Descriptor, Reading

    from redsun.utils.devices import Configuration

__all__ = ["ConfigurationTab", "DescriptorTreeView"]


def _split_key(key: str) -> tuple[str, str]:
    """Return *key*'s device and property: `cam-gain` gives `cam` and `gain`.

    A key with no `-` belongs to no device, and gives an empty device name.
    """
    owner, dash, prop = key.partition("-")
    return (owner, prop) if dash else ("", key)


def _make_value_widget(
    key: str,
    descriptor: Descriptor,
    initial_value: Any,
    on_changed: Any,
    readonly: bool,
    parent: QtWidgets.QWidget,
) -> QtWidgets.QWidget:
    """Build the editor or display widget for *descriptor*.

    Parameters
    ----------
    key
        `name-property` key, emitted with changes.
    descriptor
        `bluesky` descriptor of the setting.
    initial_value
        Current reading value.
    on_changed
        Called when the user commits a change.
    readonly
        Return a greyed label instead.
    parent
        Qt parent for the created widget.
    """
    if readonly:
        return _make_label(initial_value, parent, readonly=True)

    # not a subscript: a descriptor without a dtype fails in assert_never below
    dtype = descriptor.get("dtype")
    limits = descriptor.get("limits", {})
    control = limits.get("control", None)
    if control is not None:
        low = control.get("low", None)
        high = control.get("high", None)
    else:
        low = None
        high = None

    match dtype:
        case "array":
            return _make_label(initial_value, parent, readonly=False)

        case "integer":
            sb = QtWidgets.QSpinBox(parent)
            sb.setRange(
                int(low) if low is not None else -(2**31),
                int(high) if high is not None else 2**31 - 1,
            )
            sb.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            sb.setFrame(False)
            sb.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
            # a value is sent once it is typed, on Enter or focus out, not
            # on every keystroke on the way there
            sb.setKeyboardTracking(False)
            if isinstance(initial_value, (int, float)):
                sb.setValue(int(initial_value))
            sb.valueChanged.connect(lambda v: on_changed(key, v))
            return sb

        case "number":
            dsb = QtWidgets.QDoubleSpinBox(parent)
            dsb.setRange(
                float(low) if low is not None else -1e18,
                float(high) if high is not None else 1e18,
            )
            dsb.setDecimals(4)
            dsb.setSingleStep(0.1)
            dsb.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            dsb.setFrame(False)
            dsb.setKeyboardTracking(False)
            if isinstance(initial_value, (int, float)):
                dsb.setValue(float(initial_value))
            dsb.valueChanged.connect(lambda v: on_changed(key, v))
            return dsb

        case "string":
            choices: list[str] = descriptor.get("choices", [])
            if choices:
                cb_str = QtWidgets.QComboBox(parent)
                cb_str.addItems(choices)
                idx = cb_str.findText(
                    str(initial_value) if initial_value is not None else ""
                )
                if idx >= 0:
                    cb_str.setCurrentIndex(idx)
                cb_str.currentTextChanged.connect(lambda v: on_changed(key, v))
                return cb_str
            le = QtWidgets.QLineEdit(parent)
            le.setFrame(False)
            le.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            le.setText(str(initial_value) if initial_value is not None else "")
            le.editingFinished.connect(lambda: on_changed(key, le.text()))
            return le

        case "boolean":
            cb_bool = QtWidgets.QComboBox(parent)
            cb_bool.addItem("True", True)
            cb_bool.addItem("False", False)
            idx = cb_bool.findData(bool(initial_value))
            if idx >= 0:
                cb_bool.setCurrentIndex(idx)
            cb_bool.currentIndexChanged.connect(
                lambda _: on_changed(key, cb_bool.currentData())
            )
            return cb_bool

        case _:
            assert_never(dtype)


def _make_label(
    value: Any, parent: QtWidgets.QWidget, *, readonly: bool
) -> QtWidgets.QLabel:
    """Return a centred label showing *value*, greyed out when *readonly*."""
    # convert the initial value to a tuple
    # that can be more easily rendered as text
    if isinstance(value, np.ndarray):
        value = tuple(value.tolist())
    elif isinstance(value, (list, tuple)):
        value = tuple(value)
    lbl = QtWidgets.QLabel(parent)
    lbl.setAlignment(
        QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.AlignmentFlag.AlignVCenter
    )
    lbl.setContentsMargins(4, 0, 4, 0)
    if readonly:
        palette = lbl.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(130, 130, 130)
        )
        lbl.setPalette(palette)
    _set_label_text(lbl, value)
    return lbl


def _set_label_text(
    label: QtWidgets.QLabel,
    value: Any,
) -> None:
    """Update *label* text with *value*.

    Parameters
    ----------
    label
        Label widget to update.
    value
        New value to display.
    """
    if isinstance(value, (list, tuple)):
        label.setText(str(list(value)))
    else:
        label.setText(str(value) if value is not None else "")


def _update_widget_value(widget: QtWidgets.QWidget, value: Any) -> None:
    """Show *value* in an existing widget without emitting a change.

    Parameters
    ----------
    widget
        The editor or display widget to update.
    value
        New value to display or set.
    """
    if isinstance(widget, QtWidgets.QLabel):
        _set_label_text(widget, value)
        return
    with QtCore.QSignalBlocker(widget):
        if isinstance(widget, QtWidgets.QSpinBox):
            if isinstance(value, (int, float)):
                widget.setValue(int(value))
        elif isinstance(widget, QtWidgets.QDoubleSpinBox):
            if isinstance(value, (int, float)):
                widget.setValue(float(value))
        elif isinstance(widget, QtWidgets.QComboBox):
            # boolean combobox stores bool data; string combobox stores text
            if isinstance(value, bool) or widget.itemData(0) is True:
                idx = widget.findData(bool(value))
            else:
                idx = widget.findText(str(value) if value is not None else "")
            if idx >= 0:
                widget.setCurrentIndex(idx)
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.setText(str(value) if value is not None else "")


class DescriptorTreeView(QtWidgets.QTreeWidget):
    """Two-column property tree for browsing and editing device settings.

    Rows are grouped by their `name-property` key: one header per device
    name, and under it a header per group a property names with a dash of its
    own, so `cam-properties-Binning` is `Binning` under `properties`
    under `cam`.

    Parameters
    ----------
    descriptors
        Descriptors by `name-property` key.
    readings
        Initial readings for the same keys; only `reading["value"]` is read.
    parent
        Parent widget.
    """

    sig_property_changed = Signal(str, str, object)
    """Emitted with the object name, property name and new value of a committed edit.

    The edit stays pending until `set_value` or `revert` settles it.
    """

    def __init__(
        self,
        descriptors: dict[str, Descriptor],
        readings: dict[str, Reading[Any]],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._descriptors = descriptors
        self._readings = {k: v["value"] for k, v in readings.items()}
        self._pending: dict[str, Any] = {}
        self._widgets: dict[str, QtWidgets.QWidget] = {}

        self.setColumnCount(2)
        self.setHeaderLabels(["Setting", "Value"])
        self.setHeaderHidden(True)
        header = self.header()
        if header is not None:
            header.setSectionResizeMode(
                0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.setRootIsDecorated(False)
        self.setIndentation(12)
        self.setAlternatingRowColors(True)
        self.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        self._build()

    def set_value(self, key: str, value: Any) -> None:
        """Show *value* for *key*, the value the device holds.

        Settles an edit pending on *key*, so the row shows what the device
        read back rather than what was typed. Emits nothing. A *key* the tree
        has no row for is ignored.

        Parameters
        ----------
        key
            `name-property` key.
        """
        self._pending.pop(key, None)
        self._show(key, value)

    def set_enabled(self, owner: str, enabled: bool) -> None:
        """Enable or disable the editors of every row of *owner*.

        Parameters
        ----------
        owner
            Device name, the part of a key before its first `-`.
        """
        for key, widget in self._widgets.items():
            if _split_key(key)[0] == owner:
                widget.setEnabled(enabled)

    def revert(self, key: str) -> None:
        """Put back the value *key* had before the edit pending on it.

        For an edit the device refused. Emits nothing, and does nothing when
        no edit is pending on *key*.
        """
        if key in self._pending:
            self._show(key, self._pending.pop(key))

    def _show(self, key: str, value: Any) -> None:
        widget = self._widgets.get(key)
        if widget is None:
            return
        self._readings[key] = value
        _update_widget_value(widget, value)

    def _on_changed(self, key: str, value: Any) -> None:
        """Handle a change from any editor widget."""
        self._pending[key] = self._readings.get(key)
        self._readings[key] = value
        owner, prop = _split_key(key)
        self.sig_property_changed.emit(owner, prop, value)

    def _add_leaf(
        self,
        group_item: QtWidgets.QTreeWidgetItem,
        full_key: str,
        prop: str,
        desc: Descriptor,
        readonly: bool,
    ) -> None:
        """Append a row (setting and value widget) to *group_item*."""
        child = QtWidgets.QTreeWidgetItem()
        units = desc.get("units", "") or ""
        label = f"{prop} ({units})" if units else prop
        child.setText(0, label)
        child.setTextAlignment(
            0,
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
        )
        tip_parts = [f"dtype: {desc.get('dtype', '?')}"]
        if "units" in desc:
            tip_parts.append(f"units: {desc['units']}")
        if readonly:
            tip_parts.append("(read-only)")
        tip = " | ".join(tip_parts)
        child.setToolTip(0, tip)
        child.setToolTip(1, tip)
        group_item.addChild(child)
        initial = self._readings.get(full_key)
        widget = _make_value_widget(
            full_key, desc, initial, self._on_changed, readonly, self
        )
        self.setItemWidget(child, 1, widget)
        self._widgets[full_key] = widget

    def _make_group_item(
        self, label: str, parent: QtWidgets.QTreeWidgetItem | None = None
    ) -> QtWidgets.QTreeWidgetItem:
        """Create a bold group header, top-level or under *parent*."""
        item = QtWidgets.QTreeWidgetItem([label])
        item.setFirstColumnSpanned(True)
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        item.setExpanded(True)
        if parent is None:
            self.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    def _build(self) -> None:
        """Build the tree from each key's device name and property path."""
        owners: dict[str, QtWidgets.QTreeWidgetItem] = {}
        groups: dict[tuple[str, str], QtWidgets.QTreeWidgetItem] = {}
        for full_key, desc in self._descriptors.items():
            owner, prop = _split_key(full_key)
            source = desc.get("source", "")
            readonly = source.split("://", 1)[-1] == "readonly" or source.endswith(
                ":readonly"
            )
            if owner not in owners:
                owners[owner] = self._make_group_item(owner or "settings")
            parent = owners[owner]
            if "-" in prop:
                group, prop = prop.split("-", 1)
                if (owner, group) not in groups:
                    groups[(owner, group)] = self._make_group_item(group, parent)
                parent = groups[(owner, group)]
            self._add_leaf(parent, full_key, prop, desc, readonly)
        self.expandAll()
        self.resizeColumnToContents(0)


class ConfigurationTab(QtWidgets.QWidget):
    """The configuration of a set of devices, shown and edited in a tree.

    Says "No device has a configuration." when there is none.
    """

    sig_configure = Signal(str, object)
    """Key and value of an edit."""

    def __init__(
        self, configuration: Configuration, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._owners = {_split_key(key)[0] for key in configuration.descriptors}
        self._tree: DescriptorTreeView | None = None
        if configuration.descriptors:
            self._tree = DescriptorTreeView(
                configuration.descriptors, configuration.readings, self
            )
            self._tree.sig_property_changed.connect(self._configure)
            layout.addWidget(self._tree)
        else:
            layout.addWidget(QtWidgets.QLabel("No device has a configuration.", self))

    def update_value(self, key: str, value: object) -> None:
        """Show *value*, read back from the configuration signal *key*."""
        if self._tree is not None:
            self._tree.set_value(key, value)

    def set_locked(self, names: frozenset[str]) -> None:
        """Disable the rows of the owners in *names*, and enable the rest."""
        if self._tree is not None:
            for owner in self._owners:
                self._tree.set_enabled(owner, owner not in names)

    def _configure(self, owner: str, prop: str, value: object) -> None:
        self.sig_configure.emit(f"{owner}-{prop}" if owner else prop, value)
