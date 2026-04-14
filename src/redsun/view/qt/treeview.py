"""Descriptor-driven tree view for displaying and editing device settings.

`DescriptorTreeView` is a self-contained `QTreeWidget`-based widget that
renders Bluesky-compatible ``describe_configuration`` / ``read_configuration``
dicts as a two-column property tree.

The design is inspired by the ``ParameterTree`` widget from the
[pyqtgraph](https://github.com/pyqtgraph/pyqtgraph) library (MIT licence,
© 2012 University of North Carolina at Chapel Hill, Luke Campagnola).

Layout (two columns: *Setting* | *Value*):

```
▾ source          <- GROUP row, spans both columns, bold
    property  [widget]
    …
```

The ``source`` field of a Bluesky `Descriptor` is used as the group label.
When it carries the ``:readonly`` suffix (e.g. ``"settings:readonly"``) the
value cell is rendered as a greyed `QLabel` and cannot be edited.

The device-name root level is omitted — present one `DescriptorTreeView`
per device, e.g. inside a `QTabWidget`.

Supported ``dtype`` → widget mappings
--------------------------------------

| dtype | Widget |
|-------|--------|
| ``"integer"`` | `QSpinBox` |
| ``"number"`` | `QDoubleSpinBox` |
| ``"string"`` | `QLineEdit`, or `QComboBox` when ``choices`` are present |
| ``"boolean"`` | `QComboBox` (True / False) |
| ``"array"`` | read-only `QLabel` |
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from qtpy import QtCore, QtGui, QtWidgets

from redsun.virtual import Signal

if TYPE_CHECKING:
    from bluesky.protocols import Descriptor, Reading
    from event_model.documents import LimitsRange

__all__ = ["DescriptorTreeView"]

_log = logging.getLogger("redsun")


def _make_value_widget(
    key: str,
    descriptor: Descriptor,
    initial_value: Any,
    on_changed: Any,
    readonly: bool,
    parent: QtWidgets.QWidget,
) -> QtWidgets.QWidget:
    """Build an appropriate editor or display widget for *descriptor*.

    Parameters
    ----------
    key : str
        Canonical ``name-property`` key (used when emitting changes).
    descriptor : Descriptor
        Bluesky descriptor for this setting.
    initial_value : Any
        Current reading value.
    on_changed : Callable[[str, Any], None]
        Callable invoked when the user commits a change.
    readonly : bool
        If ``True``, return a plain greyed label.
    parent : QtWidgets.QWidget
        Qt parent for the created widget.
    """
    if readonly or descriptor.get("dtype") == "array":
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
        _set_label_text(lbl, initial_value, descriptor)
        return lbl

    dtype: str = descriptor.get("dtype", "")
    limits = cast(
        "LimitsRange",
        descriptor.get("limits", {}).get("control", {}),
    )
    low: float | None = limits.get("low", None)
    high: float | None = limits.get("high", None)
    units: str = descriptor.get("units", "") or ""

    if dtype == "integer":
        sb = QtWidgets.QSpinBox(parent)
        sb.setRange(
            int(low) if low is not None else -(2**31),
            int(high) if high is not None else 2**31 - 1,
        )
        if units:
            sb.setSuffix(f" {units}")
        sb.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        sb.setFrame(False)
        sb.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        if isinstance(initial_value, (int, float)):
            sb.setValue(int(initial_value))
        sb.valueChanged.connect(lambda v: on_changed(key, v))
        return sb

    if dtype == "number":
        dsb = QtWidgets.QDoubleSpinBox(parent)
        dsb.setRange(
            float(low) if low is not None else -1e18,
            float(high) if high is not None else 1e18,
        )
        dsb.setDecimals(4)
        dsb.setSingleStep(0.1)
        if units:
            dsb.setSuffix(f" {units}")
        dsb.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        dsb.setFrame(False)
        dsb.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        if isinstance(initial_value, (int, float)):
            dsb.setValue(float(initial_value))
        dsb.valueChanged.connect(lambda v: on_changed(key, v))
        return dsb

    if dtype == "string":
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

    if dtype == "boolean":
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

    # "array" and unknown dtypes: plain label
    fallback = QtWidgets.QLabel(
        str(initial_value) if initial_value is not None else "", parent
    )
    fallback.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    fallback.setContentsMargins(4, 0, 4, 0)
    return fallback


def _set_label_text(
    label: QtWidgets.QLabel,
    value: Any,
    descriptor: Descriptor,
) -> None:
    """Update *label* text with value + optional unit suffix.

    Parameters
    ----------
    label : QtWidgets.QLabel
        Label widget to update.
    value : Any
        New value to display.
    descriptor : Descriptor
        Bluesky descriptor; ``units`` is read from it when present.
    """
    units: str = (descriptor.get("units", "") or "") if descriptor else ""
    suffix = f" {units}" if units else ""
    if isinstance(value, (list, tuple)):
        label.setText(f"{list(value)}{suffix}")
    else:
        label.setText(f"{value}{suffix}" if value is not None else "")


def _update_widget_value(
    widget: QtWidgets.QWidget, value: Any, descriptor: Descriptor
) -> None:
    """Push a new *value* into an existing editor/display widget without re-emitting.

    Parameters
    ----------
    widget : QtWidgets.QWidget
        The editor or display widget to update.
    value : Any
        New value to display or set.
    descriptor : Descriptor
        Bluesky descriptor for this setting.
    """
    if isinstance(widget, QtWidgets.QLabel):
        _set_label_text(widget, value, descriptor)
    elif isinstance(widget, QtWidgets.QSpinBox):
        widget.blockSignals(True)
        if isinstance(value, (int, float)):
            widget.setValue(int(value))
        widget.blockSignals(False)
    elif isinstance(widget, QtWidgets.QDoubleSpinBox):
        widget.blockSignals(True)
        if isinstance(value, (int, float)):
            widget.setValue(float(value))
        widget.blockSignals(False)
    elif isinstance(widget, QtWidgets.QComboBox):
        widget.blockSignals(True)
        # boolean combobox stores bool data; string combobox stores text
        if isinstance(value, bool) or widget.itemData(0) is True:
            idx = widget.findData(bool(value))
        else:
            idx = widget.findText(str(value) if value is not None else "")
        if idx >= 0:
            widget.setCurrentIndex(idx)
        widget.blockSignals(False)
    elif isinstance(widget, QtWidgets.QLineEdit):
        widget.blockSignals(True)
        widget.setText(str(value) if value is not None else "")
        widget.blockSignals(False)


class DescriptorTreeView(QtWidgets.QTreeWidget):
    """Two-column property tree for browsing and editing device settings.

    Modelled after the pyqtgraph ``ParameterTree``: uses ``setItemWidget``
    to place editor/display widgets permanently in the *Value* column, so
    there are no popup editors and no delegate geometry issues.

    The device-name root level is omitted — use one widget per device,
    e.g. inside a ``QTabWidget``.

    Two construction forms are supported:

    **Flat form** — a single device's pre-resolved dicts, grouped by the
    ``source`` field prefix of each descriptor:

    ```python
    view = DescriptorTreeView(
        device.describe_configuration(),
        device.read_configuration(),
        parent,
    )
    ```

    **Grouped form** — data collected from a device tree by the presenter
    layer, one tuple per device; groups tree rows by device name rather
    than source prefix:

    ```python
    groups = [
        ("stage-x", stage.x.describe_configuration(), stage.x.read_configuration()),
        ("stage-y", stage.y.describe_configuration(), stage.y.read_configuration()),
    ]
    view = DescriptorTreeView(groups, parent)
    ```

    Parameters
    ----------
    descriptors_or_groups : dict[str, Descriptor] or list[tuple[str, dict[str, Descriptor], dict[str, Reading[Any]]]]
        Either a flat descriptor dict (first form) or a list of
        ``(device_name, descriptors, readings)`` tuples (second form).
    readings_or_parent : dict[str, Reading[Any]] or QtWidgets.QWidget or None
        Flat reading dict when using the first form; optional parent
        widget when using the second form.
    parent : QtWidgets.QWidget, optional
        Optional parent widget (first form only).

    Signals
    -------
    sigPropertyChanged : Signal[str, Any]
        Emitted when the user commits an edit.
        Carries ``(key: str, value: Any)``.
    """

    sigPropertyChanged: Signal = Signal(str, object)

    def __init__(
        self,
        descriptors: dict[str, Descriptor] | None = None,
        readings: dict[str, Reading[Any]] | None = None,
        groups: list[tuple[str, dict[str, Descriptor], dict[str, Reading[Any]]]]
        | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        if groups is not None:
            # grouped form: [(device_name, descriptors, readings), ...]
            _descriptors: dict[str, Descriptor] = {}
            _readings: dict[str, Reading[Any]] = {}
            group_keys: list[tuple[str, list[str]]] = []
            for dev_name, desc, read in groups:
                _descriptors.update(desc)
                _readings.update(read)
                if desc:
                    group_keys.append((dev_name, list(desc.keys())))
            self._groups: list[tuple[str, list[str]]] | None = group_keys
            descriptors = _descriptors
            readings = _readings
        else:
            # flat form: (descriptors, readings)
            descriptors = descriptors or {}
            readings = readings or {}
            self._groups = None

        self._descriptors: dict[str, Descriptor] = descriptors
        self._readings: dict[str, Any] = {k: v["value"] for k, v in readings.items()}
        self._pending: dict[str, Any] = {}
        self._widgets: dict[str, QtWidgets.QWidget] = {}

        self.setColumnCount(2)
        self.setHeaderLabels(["Setting", "Value"])
        self.setHeaderHidden(True)
        _hdr = self.header()
        if _hdr is not None:
            _hdr.setSectionResizeMode(
                0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
            _hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.setRootIsDecorated(False)
        self.setIndentation(12)
        self.setAlternatingRowColors(True)
        self.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        self._build()

    def update_reading(self, key: str, reading: Reading[Any]) -> None:
        """Push a live value update for *key* into the corresponding widget.

        Parameters
        ----------
        key : str
            Canonical ``name-property`` key.
        reading : Reading[Any]
            New reading dict; only ``reading["value"]`` is used.
        """
        value = reading["value"]
        self._readings[key] = value
        widget = self._widgets.get(key)
        if widget is not None:
            desc = self._descriptors.get(key)
            if desc is not None:
                _update_widget_value(widget, value, desc)

    def confirm_change(self, key: str, success: bool) -> None:
        """Confirm or revert a pending user edit.

        Parameters
        ----------
        key : str
            Canonical key of the setting that was attempted.
        success : bool
            ``True`` → keep the new value; ``False`` → revert to the
            pre-edit value and refresh the widget.
        """
        old = self._pending.pop(key, None)
        if old is None:
            return
        if not success:
            self._readings[key] = old
            widget = self._widgets.get(key)
            desc = self._descriptors.get(key)
            if widget is not None and desc is not None:
                _update_widget_value(widget, old, desc)
            _log.info("Reverted '%s' to previous value.", key)

    def get_keys(self) -> set[str]:
        """Return the set of all descriptor keys in this view."""
        return set(self._descriptors.keys())

    def _on_changed(self, key: str, value: Any) -> None:
        """Slot wired to every editor widget's change signal."""
        self._pending[key] = self._readings.get(key)
        self._readings[key] = value
        self.sigPropertyChanged.emit(key, value)

    def _add_leaf(
        self,
        group_item: QtWidgets.QTreeWidgetItem,
        full_key: str,
        prop: str,
        desc: Descriptor,
        readonly: bool,
    ) -> None:
        """Append one leaf row (setting + value widget) to *group_item*."""
        child = QtWidgets.QTreeWidgetItem()
        child.setText(0, prop)
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

    def _make_group_item(self, label: str) -> QtWidgets.QTreeWidgetItem:
        """Create and register a bold top-level group header item."""
        item = QtWidgets.QTreeWidgetItem([label])
        item.setFirstColumnSpanned(True)
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        item.setExpanded(True)
        self.addTopLevelItem(item)
        return item

    def _build(self) -> None:
        """Populate the tree from ``self._descriptors`` and ``self._readings``.

        Delegates to :meth:`_build_from_groups` when device-name groups are
        available (set by :meth:`from_device`), otherwise falls back to
        :meth:`_build_from_sources` which groups by the ``source`` field
        prefix of each descriptor.
        """
        self.clear()
        self._widgets.clear()
        if self._groups is not None:
            self._build_from_groups()
        else:
            self._build_from_sources()
        self.expandAll()
        self.resizeColumnToContents(0)

    def _build_from_groups(self) -> None:
        """Build tree with one top-level group per device name.

        Used when the tree was constructed via :meth:`from_device`.
        The group label is the device's :attr:`~redsun.device.Device.name`;
        the leaf label strips that name prefix from the full key so only the
        bare property name is shown (e.g. ``stage-x-position`` → ``position``
        under the ``Stage X`` group).
        """
        assert self._groups is not None
        for device_name, keys in self._groups:
            label = device_name.replace("-", " ").title()
            group_item = self._make_group_item(label)
            prefix = f"{device_name}-"
            for full_key in keys:
                desc = self._descriptors[full_key]
                prop = (
                    full_key[len(prefix) :] if full_key.startswith(prefix) else full_key
                )
                source_raw: str = desc.get("source", "")
                readonly = ":readonly" in source_raw
                self._add_leaf(group_item, full_key, prop, desc, readonly)

    def _build_from_sources(self) -> None:
        """Build tree grouped by the ``source`` field prefix of each descriptor.

        This is the legacy path used when :meth:`__init__` is called directly
        with pre-built flat dicts rather than via :meth:`from_device`.
        """
        groups: dict[str, list[tuple[str, str, Descriptor, bool]]] = {}
        for full_key, desc in self._descriptors.items():
            prop = full_key.split("-", 1)[-1] if "-" in full_key else full_key
            source_raw: str = desc.get("source", "unknown")
            parts = source_raw.split(":", 1)
            source = parts[0]
            readonly = len(parts) > 1 and parts[1] == "readonly"
            groups.setdefault(source, []).append((full_key, prop, desc, readonly))

        for source, leaves in groups.items():
            group_item = self._make_group_item(source.title())
            for full_key, prop, desc, readonly in leaves:
                self._add_leaf(group_item, full_key, prop, desc, readonly)
