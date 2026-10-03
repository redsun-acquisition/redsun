"""Tests for the positioner view."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

import pytest
from qtpy import QtCore, QtGui, QtWidgets
from superqt import QCollapsible, QLabeledSlider

from redsun import Settings
from redsun.presenter import DescribesAxes
from redsun.utils.devices import AxisInfo, Configuration
from redsun.view.qt.builtins import PositionerGroup, PositionerView
from redsun.view.qt.treeview import DescriptorTreeView

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.qt

T = TypeVar("T", bound=QtCore.QObject)

AXES = {
    "stage": {"x": AxisInfo(0.0, "um", 3), "theta": AxisInfo(0.0, "deg", 1)},
    "focus": {"focus": AxisInfo(52.1, "um", 2)},
}


class MarkedGroup(PositionerGroup):
    """A group with a button of its own."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.extra = QtWidgets.QPushButton("Home", self)


class CustomView(PositionerView):
    """A positioner view with its own groups and a tab of its own."""

    group_class = MarkedGroup

    def setup(self, positioner: DescribesAxes, settings: Settings) -> None:
        super().setup(positioner, settings)
        self.tabs.addTab(QtWidgets.QLabel("notes"), "Notes")


class Positioner:
    """Describes two devices, as a positioner presenter would."""

    axes = AXES
    configuration = Configuration(
        descriptors={
            "stage-axis-x-velocity": {
                "source": "soft://v",
                "dtype": "number",
                "shape": [],
            }
        },
        readings={"stage-axis-x-velocity": {"value": 1.0, "timestamp": 0.0}},
        writable={},
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(tmp_path / "session.json")


@pytest.fixture
def parent(qapp: QtWidgets.QApplication) -> QtWidgets.QWidget:
    return QtWidgets.QWidget()


def make_view(
    settings: Settings, parent: QtWidgets.QWidget, repeat_interval: int = 50
) -> PositionerView:
    """Build a positioner view on two devices, in *parent*."""
    view = PositionerView("positioner", parent, repeat_interval=repeat_interval)
    view.setup(Positioner(), settings)
    return view


def child(parent: QtCore.QObject, kind: type[T], name: str = "") -> T:
    """Return the child of *parent* of type *kind*, named *name* when given."""
    found = parent.findChild(kind, name) if name else parent.findChild(kind)
    assert found is not None
    return found


def group(view: PositionerView, device: str) -> PositionerGroup:
    """Return the group of *device* in *view*."""
    found = [g for g in view.findChildren(PositionerGroup) if g.title() == device]
    assert len(found) == 1
    return found[0]


def type_into(edit: QtWidgets.QLineEdit, text: str) -> None:
    """Replace the text of *edit* by typing *text*, then press Enter."""
    edit.selectAll()
    keys = [(0, char) for char in text] + [(QtCore.Qt.Key.Key_Return, "")]
    for key, char in keys:
        for kind in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
            event = QtGui.QKeyEvent(
                kind, key, QtCore.Qt.KeyboardModifier.NoModifier, char
            )
            QtWidgets.QApplication.sendEvent(edit, event)


def shown_names(view: PositionerView) -> list[str]:
    """Return the names of the saved positions *view* shows."""
    edits = [
        e
        for e in view.findChildren(QtWidgets.QLineEdit)
        if e.objectName().startswith("saved:")
    ]
    return [e.text() for e in sorted(edits, key=lambda e: e.objectName())]


def test_each_device_gets_a_group_whose_requests_the_view_sends(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Build a group per device and send its steps and go-tos on."""
    view = make_view(settings, parent)
    moves: list[object] = []
    view.sig_move.connect(lambda *args: moves.append(args))
    view.sig_move_to.connect(lambda *args: moves.append(args))

    group(view, "stage").sig_move.emit("stage", "x", 1.0)
    group(view, "focus").sig_move_to.emit("focus", {"focus": 50.0})

    assert {g.title() for g in view.findChildren(PositionerGroup)} == {"stage", "focus"}
    assert moves == [("stage", "x", 1.0), ("focus", {"focus": 50.0})]


def test_slots_reach_the_group_of_their_device(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Pass readbacks, states and locks to the group of each device."""
    view = make_view(settings, parent)

    view.update_readback("stage", "x", 4.0)
    view.set_moving("focus", True)
    view.set_failed("stage", "out of range")
    view.set_locked(frozenset({"focus"}))

    assert group(view, "stage").positions["x"] == 4.0
    assert child(group(view, "focus"), QtWidgets.QLabel, "state").text() == "moving"
    assert child(group(view, "stage"), QtWidgets.QLabel, "state").text() == (
        "failed: out of range"
    )
    assert not child(
        group(view, "focus"), QtWidgets.QAbstractButton, "save"
    ).isEnabled()
    assert child(group(view, "stage"), QtWidgets.QAbstractButton, "save").isEnabled()


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        pytest.param("5", 10, id="below"),
        pytest.param("400", 300, id="above"),
        pytest.param("150", 150, id="inside"),
    ],
)
def test_a_typed_repeat_interval_stays_in_range_and_is_kept(
    parent: QtWidgets.QWidget, settings: Settings, typed: str, expected: int
) -> None:
    """Clamp a typed repeat interval to 10-300 ms, apply it and keep it."""
    view = make_view(settings, parent)
    slider = child(view, QLabeledSlider)

    type_into(child(slider, QtWidgets.QLineEdit), typed)

    plus = child(group(view, "stage"), QtWidgets.QAbstractButton, "plus:x")
    assert slider.value() == expected
    assert plus.autoRepeatInterval() == expected
    assert child(make_view(settings, parent), QLabeledSlider).value() == expected


def test_a_configuration_edit_is_sent_on(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Send an edit of the configuration tree as a key and value."""
    view = make_view(settings, parent)
    sent: list[tuple[str, object]] = []
    view.sig_configure.connect(lambda *args: sent.append(args))
    stops: list[str] = []
    view.sig_stop.connect(stops.append)

    child(view, DescriptorTreeView).sig_property_changed.emit(
        "stage", "axis-x-velocity", 2.0
    )
    view.update_configuration("stage-axis-x-velocity", 2.0)
    group(view, "stage").sig_stop.emit("stage")

    assert sent == [("stage-axis-x-velocity", 2.0)]
    assert stops == ["stage"]


def test_a_subclass_chooses_its_groups_and_adds_a_tab(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Build the subclass' group for each device and keep the tab it adds."""
    view = CustomView("positioner", parent)
    view.setup(Positioner(), settings)

    groups = view.findChildren(PositionerGroup)
    assert len(groups) == 2
    assert all(isinstance(g, MarkedGroup) for g in groups)
    labels = [view.tabs.tabText(i) for i in range(view.tabs.count())]
    assert labels == ["Motors", "Configuration", "Advanced", "Notes"]


def test_the_repeat_interval_defaults_to_the_keyword(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Start at the keyword's interval when the settings hold none."""
    view = make_view(settings, parent, repeat_interval=80)

    assert child(view, QLabeledSlider).value() == 80


def test_a_saved_position_outlives_the_view_and_moves_its_device(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Save readbacks, rename the entry, find it in a new view and go there."""
    view = make_view(settings, parent)
    view.update_readback("stage", "x", 12.5)
    child(group(view, "stage"), QtWidgets.QAbstractButton, "save").click()
    type_into(child(view, QtWidgets.QLineEdit, "saved:0"), "sample A")

    again = make_view(settings, parent)
    targets: list[object] = []
    again.sig_move_to.connect(lambda *args: targets.append(args))
    child(again, QtWidgets.QAbstractButton, "saved-go:0").click()

    assert shown_names(again) == ["sample A"]
    assert targets == [("stage", {"x": 12.5, "theta": 0.0})]


def test_a_removed_position_is_gone_from_the_settings(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Remove an entry from the view and from the settings."""
    view = make_view(settings, parent)
    child(group(view, "focus"), QtWidgets.QAbstractButton, "save").click()

    child(view, QtWidgets.QAbstractButton, "saved-remove:0").click()

    assert shown_names(view) == []
    assert settings.get("positioner.saved_positions") == []


def test_an_entry_for_an_absent_device_is_kept_but_not_shown(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Hide an entry whose device the session lacks, and keep it stored."""
    absent: dict[str, Any] = {"name": "old", "device": "gone", "positions": {"a": 1.0}}
    settings.set("positioner.saved_positions", [absent])
    view = make_view(settings, parent)

    child(group(view, "focus"), QtWidgets.QAbstractButton, "save").click()

    assert shown_names(view) == ["focus 1"]
    assert settings.get("positioner.saved_positions")[0] == absent


def test_an_entry_moves_only_the_axes_its_device_still_has(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Leave out of a go-to the axes the device no longer has."""
    entry: dict[str, Any] = {
        "name": "old",
        "device": "stage",
        "positions": {"x": 1.0, "z": 2.0},
    }
    settings.set("positioner.saved_positions", [entry])
    view = make_view(settings, parent)
    targets: list[object] = []
    view.sig_move_to.connect(lambda *args: targets.append(args))

    child(view, QtWidgets.QAbstractButton, "saved-go:0").click()

    assert targets == [("stage", {"x": 1.0})]


def test_malformed_entries_are_skipped_with_a_warning(
    parent: QtWidgets.QWidget, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """Skip entries that are not well formed, warn, and show the rest."""
    good: dict[str, Any] = {
        "name": "ok",
        "device": "focus",
        "positions": {"focus": 1.0},
    }
    settings.set(
        "positioner.saved_positions",
        [
            good,
            {"name": 3},
            "text",
            {"name": "x", "device": "stage", "positions": {"x": "a"}},
        ],  # mixed on purpose: what a hand-edited settings file may hold
    )

    view = make_view(settings, parent)

    assert shown_names(view) == ["ok"]
    assert "Skipping 3 saved positions" in caplog.text


def test_a_locked_device_cannot_go_to_its_saved_positions(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Disable the go button of the saved positions of a locked device."""
    view = make_view(settings, parent)
    child(group(view, "focus"), QtWidgets.QAbstractButton, "save").click()

    view.set_locked(frozenset({"focus"}))

    assert not child(view, QtWidgets.QAbstractButton, "saved-go:0").isEnabled()


def test_saving_opens_the_saved_positions(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Open the saved positions when a position is saved."""
    view = make_view(settings, parent)

    child(group(view, "focus"), QtWidgets.QAbstractButton, "save").click()

    assert child(view, QCollapsible).isExpanded()


def test_a_saved_entry_without_axes_left_moves_nothing(
    parent: QtWidgets.QWidget, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """Send no go-to for an entry none of whose axes the device still has."""
    gone: dict[str, Any] = {"name": "old", "device": "stage", "positions": {"z": 1.0}}
    settings.set("positioner.saved_positions", [gone])
    view = make_view(settings, parent)
    targets: list[object] = []
    view.sig_move_to.connect(lambda *args: targets.append(args))

    child(view, QtWidgets.QAbstractButton, "saved-go:0").click()

    assert targets == []
    assert "no axis z" in caplog.text


def test_saved_positions_that_are_not_a_list_are_reported(
    parent: QtWidgets.QWidget, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """Warn when the stored saved positions are not a list."""
    settings.set("positioner.saved_positions", {"not": "a list"})

    make_view(settings, parent)

    assert "not a list" in caplog.text


@pytest.mark.parametrize(
    ("stored", "expected"),
    [pytest.param(True, 50, id="bool"), pytest.param(1000, 300, id="too-long")],
)
def test_a_stored_repeat_interval_is_checked(
    parent: QtWidgets.QWidget, settings: Settings, stored: int, expected: int
) -> None:
    """Ignore a stored interval that is not a number, and clamp one too long."""
    settings.set("positioner.repeat_interval", stored)

    assert child(make_view(settings, parent), QLabeledSlider).value() == expected


def test_a_locked_device_cannot_be_configured_until_released(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Disable the configuration rows of a locked device, and enable them after."""
    view = make_view(settings, parent)
    tree = child(view, DescriptorTreeView)
    editors = [w for w in tree.findChildren(QtWidgets.QWidget) if w.isEnabled()]

    view.set_locked(frozenset({"stage"}))
    locked = [w for w in editors if not w.isEnabled()]
    view.set_locked(frozenset())

    assert locked
    assert all(w.isEnabled() for w in editors)


def test_the_view_fits_a_narrow_dock(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Keep the view within 26 digits of its font: about 190 px at 9 pt."""
    view = make_view(settings, parent)
    digit = view.fontMetrics().horizontalAdvance("0")

    assert view.minimumSizeHint().width() <= 26 * digit


def test_a_name_freed_by_a_removal_is_used_again(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Name a new saved position after the lowest number no entry uses."""
    view = make_view(settings, parent)
    save = child(group(view, "focus"), QtWidgets.QAbstractButton, "save")
    save.click()
    save.click()

    child(view, QtWidgets.QAbstractButton, "saved-remove:0").click()
    save.click()

    assert shown_names(view) == ["focus 2", "focus 1"]


def test_a_lock_holds_when_the_saved_positions_are_rebuilt(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Keep a locked device's saved Go disabled after another entry is added."""
    view = make_view(settings, parent)
    child(group(view, "focus"), QtWidgets.QAbstractButton, "save").click()
    view.set_locked(frozenset({"focus"}))

    child(group(view, "stage"), QtWidgets.QAbstractButton, "save").click()

    assert not child(view, QtWidgets.QAbstractButton, "saved-go:0").isEnabled()
    assert child(view, QtWidgets.QAbstractButton, "saved-go:1").isEnabled()
