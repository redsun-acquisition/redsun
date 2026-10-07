"""Tests for the widgets of values built from other values."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Annotated, Any, Literal

import pytest
from annotated_types import Ge, Gt, Le, Lt, MaxLen, MultipleOf
from magicgui.widgets.bases import BaseValueWidget, RangedWidget
from qtpy import QtWidgets

from redsun.view.qt._value_widgets import problems_of, widget_options
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
        (int | bool, True),
        (list[int] | list[str], ["a"]),
        (dict[str, int] | dict[str, float], {"a": 1.5}),
        (list[Annotated[float, {"min": -5.0}]], [1.0]),
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


def test_a_union_takes_a_default_its_member_holds_in_another_container(
    qapp: QtWidgets.QApplication,
) -> None:
    """Start a union on the member a tuple default fits, and return it as that member's list."""
    assert build("delay", float | Sequence[float], (0.1, 0.2)).value == [0.1, 0.2]


def test_a_default_no_input_can_show_leaves_the_input_empty(
    qapp: QtWidgets.QApplication,
) -> None:
    """Build an input from its own start when the default does not fit the annotation."""
    assert build("x", list[int], ["a"]).value == [0]


def test_each_member_of_a_union_has_its_own_name(
    qapp: QtWidgets.QApplication,
) -> None:
    """Name union members apart, so each one can be chosen."""
    widget = build("x", dict[str, int] | dict[str, float] | Literal["a", "b"], "a")
    [choice] = widget.native.findChildren(QtWidgets.QComboBox)[:1]

    assert [choice.itemText(i) for i in range(choice.count())] == [
        "dict of str to int",
        "dict of str to float",
        "'a' or 'b'",
    ]


def test_a_union_refuses_a_value_no_member_holds(
    qapp: QtWidgets.QApplication,
) -> None:
    """Raise rather than drop a value set on a union that no member can show."""
    widget = build("delay", float | list[float], 0.0)

    with pytest.raises(ValueError, match="no member"):
        widget.value = "soon"


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (Annotated[int, Ge(1), Le(9)], {"min": 1, "max": 9}),
        (Annotated[int, Gt(0), Lt(10)], {"min": 1, "max": 9}),
        (Annotated[float, Gt(0), Le(10)], {"min": 0, "max": 10}),
        (Annotated[float, MultipleOf(0.001)], {"step": 0.001}),
        (Annotated[int, Le(10), {"max": 20}], {"max": 10}),
        (Annotated[int, {"max": 20}], {"max": 20}),
    ],
)
def test_limits_become_widget_options(
    annotation: Any, expected: dict[str, Any]
) -> None:
    """Turn limits into min, max and step, a limit beating a conflicting dict."""
    options = widget_options(annotation)

    assert {key: options[key] for key in expected} == expected


@pytest.mark.parametrize(
    ("annotation", "low", "high"),
    [
        (float, -math.inf, math.inf),
        (int, -(2**31), 2**31 - 1),
    ],
)
def test_a_number_without_a_bound_has_no_range_limit(
    qapp: QtWidgets.QApplication, annotation: Any, low: float, high: float
) -> None:
    """Give an unbounded number the widest range its widget allows, not 0 to 999."""
    widget = build("value", annotation, default=0)

    assert isinstance(widget, RangedWidget)
    assert (widget.min, widget.max) == (low, high)


def test_a_slider_and_a_bool_keep_their_own_range() -> None:
    """Leave a slider's finite range and a bool's widget alone."""
    assert "min" not in widget_options(Annotated[float, {"widget_type": "FloatSlider"}])
    assert widget_options(bool) == {}


def test_a_step_with_more_digits_shows_more_decimals(
    qapp: QtWidgets.QApplication,
) -> None:
    """Show as many decimals as a MultipleOf step needs."""
    widget = build("exposure", Annotated[float, MultipleOf(0.001)], default=0.001)

    assert widget.native.decimals() == 3


def test_a_list_stops_growing_at_its_maximum_length(
    qapp: QtWidgets.QApplication,
) -> None:
    """Disable the add button once a list holds as many items as its limit allows."""
    widget = build("points", Annotated[list[float], MaxLen(2)], default=[0.0])
    [add] = buttons(widget, "+")

    add.click()

    assert not add.isEnabled()
    [remove, _] = buttons(widget, "-")
    remove.click()
    assert add.isEnabled()


@pytest.mark.parametrize(
    ("annotation", "default"),
    [
        (Annotated[int, {"choices": [1, 2, 3]}], 2),
        (Annotated[float, {"choices": [0.5, 1.0]}], 1.0),
        (Annotated[int, Ge(0), {"choices": [1, 2]}], 2),
        (Annotated[datetime, Gt(datetime(2020, 1, 1))], datetime(2021, 1, 1)),
        (Annotated[str, MaxLen(3)], "ab"),
    ],
)
def test_a_widget_that_takes_no_range_still_builds(
    qapp: QtWidgets.QApplication, annotation: Any, default: Any
) -> None:
    """Build a choice box, a date or a text field whose annotation carries limits or choices."""
    widget = build("value", annotation, default=default)

    assert widget.value == default
