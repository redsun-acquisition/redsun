"""Tests for the widgets of values built from other values."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from magicgui.widgets.bases import BaseValueWidget
from qtpy import QtWidgets

from redsun.view.qt._value_widgets import problems_of
from redsun.view.qt._widget_factory import create_param_widget
from tests.sdk.mocks import param
from tests.sdk.view.helpers import type_into

pytestmark = pytest.mark.qt


def build(name: str, annotation: Any, default: Any) -> BaseValueWidget[Any]:
    """Return the widget a parameter with *annotation* and *default* gets."""
    widget = create_param_widget(param(name, annotation, default=default))
    assert isinstance(widget, BaseValueWidget)
    return widget


def buttons(widget: Any, text: str) -> list[QtWidgets.QPushButton]:
    """Return the push buttons labelled *text* inside *widget*, in order."""
    return [
        button
        for button in widget.native.findChildren(QtWidgets.QPushButton)
        if button.text() == text
    ]


def text_fields(widget: Any) -> list[QtWidgets.QLineEdit]:
    """Return the text fields inside *widget*, leaving out those of spin boxes."""
    return [
        field
        for field in widget.native.findChildren(QtWidgets.QLineEdit)
        if not isinstance(field.parent(), QtWidgets.QAbstractSpinBox)
    ]


@pytest.mark.parametrize(
    ("annotation", "default"),
    [
        (list[int], [1, 2]),
        (tuple[int, int], (3, 4)),
        (tuple[float, ...], (1.0, 2.0)),
        (set[int], {1, 2}),
        (frozenset[str], frozenset({"a"})),
        (Iterable[int], [5]),
        (dict[str, float], {"x": 1.0, "y": 2.0}),
        (dict[str, list[float]], {"a": [1.0, 2.0]}),
        (int | None, None),
        (int | None, 5),
        (str | None, None),
        (float | list[float], 0.0),
        (float | list[float], [1.0]),
        (list[int | None], [1, None]),
    ],
)
def test_an_untouched_widget_returns_the_default(
    qapp: QtWidgets.QApplication, annotation: Any, default: Any
) -> None:
    """Return the parameter's default, of its own type, from an untouched widget."""
    value = build("x", annotation, default).value

    assert (type(value), value) == (type(default), default)


def test_editing_a_list_leaves_the_plans_default_alone(
    qapp: QtWidgets.QApplication,
) -> None:
    """Change the widget's value, never the list the plan holds as its default."""
    default = [1, 2]
    widget = build("x", list[int], default)

    buttons(widget, "-")[0].click()

    assert (widget.value, default) == ([2], [1, 2])


def test_a_repeated_key_is_reported_until_it_is_changed(
    qapp: QtWidgets.QApplication,
) -> None:
    """Report a key typed twice, and stop once it differs."""
    widget = build("gains", dict[str, int], {"a": 1})
    buttons(widget, "+")[0].click()
    _, added = text_fields(widget)

    type_into(added, "a")
    repeated = problems_of(widget)
    added.clear()
    type_into(added, "b")

    assert repeated == ["duplicate key: 'a'"]
    assert (problems_of(widget), widget.value) == ([], {"a": 1, "b": 0})


def test_an_added_row_with_an_empty_key_is_reported(
    qapp: QtWidgets.QApplication,
) -> None:
    """Report an empty text key, at any depth."""
    widget = build("tables", list[dict[str, int]], [{"a": 1}])

    buttons(widget, "+")[1].click()

    assert problems_of(widget) == ["[0]: empty key"]


def test_an_optional_value_is_none_until_set(qapp: QtWidgets.QApplication) -> None:
    """Send None while unticked, with the input disabled, and the input's value once ticked."""
    widget = build("frames", int | None, None)
    [box] = widget.native.findChildren(QtWidgets.QCheckBox)
    [spin] = widget.native.findChildren(QtWidgets.QAbstractSpinBox)

    unset = (widget.value, spin.isEnabled())
    box.click()
    spin.setValue(4)

    assert unset == (None, False)
    assert (widget.value, spin.isEnabled()) == (4, True)


def test_a_union_returns_the_chosen_members_value(
    qapp: QtWidgets.QApplication,
) -> None:
    """Offer each member of a union by name, and return the chosen one's value."""
    widget = build("delay", float | list[float], 0.0)
    [choice] = widget.native.findChildren(QtWidgets.QComboBox)

    choice.setCurrentText("list of float")
    buttons(widget, "+")[0].click()

    assert [choice.itemText(i) for i in range(choice.count())] == [
        "float",
        "list of float",
    ]
    assert widget.value == [0.0]
