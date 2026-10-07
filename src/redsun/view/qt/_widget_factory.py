"""Widgets for plan parameter forms.

`create_param_widget` maps a `ParamDescription` to a `magicgui` widget. It
walks `WIDGET_FACTORY_MAP`, an ordered list of `(predicate, factory)` pairs,
and calls the first factory whose predicate matches.

Every other parameter gets the widget `create_value_widget` builds, which
nests the widgets of lists, sets, mappings, tuples, optional values and
unions.

Extending the system
--------------------
For a new annotation shape, write a predicate and a factory and insert the pair
at the right priority in `WIDGET_FACTORY_MAP`.

Unresolvable annotations
------------------------
`create_param_widget` raises `RuntimeError` if every entry fails, instead of
falling back silently.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias, cast

from magicgui import widgets as mgw
from magicgui.types import Undefined

from redsun.presenter.plan_spec import ParamDescription, ParamKind
from redsun.presenter.utils import isdevice, isdevicesequence, isdeviceset

from ._device_sequence_edit import DeviceSequenceEdit
from ._value_widgets import create_value_widget

WidgetPredicate: TypeAlias = Callable[[ParamDescription], bool]
WidgetFactory: TypeAlias = Callable[[ParamDescription], mgw.Widget]


def is_hidden_or_action(p: ParamDescription) -> bool:
    """Return true for parameters that should not get a normal input widget."""
    return p.actions is not None or p.hidden


def is_multiselect_device(p: ParamDescription) -> bool:
    """Return true for Sequence[PDevice], Set[PDevice], or variadic *args: PDevice parameters."""
    is_ann_model_seq = isdevicesequence(p.annotation)
    is_ann_model_set = isdeviceset(p.annotation)
    is_var_model = p.kind is ParamKind.VAR_POSITIONAL and isdevice(p.annotation)
    return is_ann_model_seq or is_ann_model_set or is_var_model


def is_singleselect_device(p: ParamDescription) -> bool:
    """Return true for single PDevice parameters."""
    return isdevice(p.annotation)


def is_literal_choices(p: ParamDescription) -> bool:
    """Return true for parameters with choices.

    Device parameters carry choices too, and match an earlier entry.
    """
    return p.choices is not None


def always(p: ParamDescription) -> bool:
    """Match anything."""
    return True


def make_dummy(p: ParamDescription) -> mgw.Widget:
    """Return a read-only LineEdit placeholder for hidden/action params."""
    return mgw.LineEdit(name=p.name)


def make_device_sequence_edit(p: ParamDescription) -> mgw.Widget:
    """Return a DeviceSequenceEdit for Sequence[PDevice] / Set[PDevice] parameters."""
    choices = p.choices or []
    initial: list[str] = []
    if p.has_default:
        d = p.default
        if isinstance(d, str):
            initial = [d]
        elif isinstance(d, (list, tuple, set, frozenset)):
            initial = list(d)
    return DeviceSequenceEdit(name=p.name, choices=choices, value=initial)


def make_singleselect_device(p: ParamDescription) -> mgw.Widget:
    """Return a ComboBox selecting one PDevice."""
    choices = p.choices or []
    return mgw.ComboBox(
        name=p.name,
        choices=choices,
        value=p.default
        if p.has_default and p.default in choices
        else (choices[0] if choices else None),
    )


def make_literal_combobox(p: ParamDescription) -> mgw.Widget:
    """Return a ComboBox of Literal[...] choices."""
    assert p.choices is not None
    return mgw.ComboBox(
        name=p.name,
        choices=p.choices,
        value=p.default if p.has_default else p.choices[0],
    )


def make_value_widget(p: ParamDescription) -> mgw.Widget:
    """Return the widget `create_value_widget` builds for the annotation.

    Raises TypeError or ValueError if no widget exists for it.
    """
    return cast(
        "mgw.Widget",
        create_value_widget(
            p.annotated, p.default if p.has_default else Undefined, name=p.name
        ),
    )


WIDGET_FACTORY_MAP: list[tuple[WidgetPredicate, WidgetFactory]] = [
    (is_hidden_or_action, make_dummy),
    (is_multiselect_device, make_device_sequence_edit),
    (is_singleselect_device, make_singleselect_device),
    (is_literal_choices, make_literal_combobox),
    (always, make_value_widget),
]


def create_param_widget(param: ParamDescription) -> mgw.Widget:
    """Create a `magicgui` widget for *param*.

    Only the predicates are guarded: a factory raising is a bug and propagates.

    Raises
    ------
    RuntimeError
        If every entry in `WIDGET_FACTORY_MAP` fails.
    """
    for predicate, factory in WIDGET_FACTORY_MAP:
        try:
            matched = predicate(param)
        except Exception:  # noqa: BLE001, S112 - a failing predicate means "no match", never a crash
            continue
        if matched:
            return factory(param)
    raise RuntimeError(
        f"No widget factory matched parameter {param.name!r} "
        f"(annotation: {param.annotation!r}). "
        f"This is a bug - create_plan_spec should have caught this."
    )
