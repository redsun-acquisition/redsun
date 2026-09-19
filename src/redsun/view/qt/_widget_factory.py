"""Widgets for plan parameter forms.

`create_param_widget` maps a `ParamDescription` to a ``magicgui`` widget. It
walks `_WIDGET_FACTORY_MAP`, an ordered list of ``(predicate, factory)`` pairs,
and calls the first factory whose predicate matches.

Extending the system
--------------------
For a new annotation shape, write a predicate and a factory and insert the pair
at the right priority in `_WIDGET_FACTORY_MAP`.

Unresolvable annotations
------------------------
`create_plan_spec` already checks that every required parameter maps to a
widget: a plan failing that raises `UnresolvableAnnotationError` and is skipped.
`create_param_widget` therefore raises `RuntimeError` if every entry fails,
instead of falling back silently.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeAlias, get_args

from magicgui import widgets as mgw
from magicgui.types import Undefined

from redsun.presenter.plan_spec import ParamDescription, ParamKind
from redsun.presenter.utils import isdevice, isdevicesequence, isdeviceset, issequence

from ._device_sequence_edit import DeviceSequenceEdit


def _is_hidden_or_action(p: ParamDescription) -> bool:
    """Return true for parameters that should not get a normal input widget."""
    return p.actions is not None or p.hidden


def _is_multiselect_device(p: ParamDescription) -> bool:
    """Return true for Sequence[PDevice], Set[PDevice], or variadic *args: PDevice parameters."""
    is_ann_model_seq = isdevicesequence(p.annotation)
    is_ann_model_set = isdeviceset(p.annotation)
    is_var_model = p.kind is ParamKind.VAR_POSITIONAL and isdevice(p.annotation)
    return is_ann_model_seq or is_ann_model_set or is_var_model


def _is_singleselect_device(p: ParamDescription) -> bool:
    """Return true for single PDevice parameters with a choices list."""
    return isdevice(p.annotation)


def _is_literal_choices(p: ParamDescription) -> bool:
    """Return true for parameters whose choices come from a Literal annotation."""
    return (
        p.choices is not None
        and not isdevice(p.annotation)
        and not isdevicesequence(p.annotation)
        and not isdeviceset(p.annotation)
    )


def _is_non_device_sequence(p: ParamDescription) -> bool:
    """Return true for Sequence[T] parameters where T is not a PDevice type."""
    return (
        issequence(p.annotation)
        and not isdevicesequence(p.annotation)
        and not isdeviceset(p.annotation)
        and not isinstance(p.annotation, (str, bytes))
    )


def _always(p: ParamDescription) -> bool:
    """Match anything."""
    return True


def _make_dummy(p: ParamDescription) -> mgw.Widget:
    """Return a read-only LineEdit placeholder for hidden/action params."""
    return mgw.LineEdit(name=p.name)


def _make_device_sequence_edit(p: ParamDescription) -> mgw.Widget:
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


def _make_singleselect_device(p: ParamDescription) -> mgw.Widget:
    """Return a ComboBox selecting one PDevice."""
    choices = p.choices or []
    return mgw.ComboBox(
        name=p.name,
        choices=choices,
        value=p.default
        if p.has_default and p.default in choices
        else (choices[0] if choices else None),
    )


def _make_literal_combobox(p: ParamDescription) -> mgw.Widget:
    """Return a ComboBox of Literal[...] choices."""
    assert p.choices is not None
    return mgw.ComboBox(
        name=p.name,
        choices=p.choices,
        value=p.default if p.has_default else p.choices[0],
    )


def _make_list_edit(p: ParamDescription) -> mgw.Widget:
    """Return a ListEdit for non-device Sequence[T] parameters."""
    actual_annotation: type[Any] = Any
    args: tuple[type[Any], ...] = get_args(p.annotation)
    arg = args[0] if args else None
    if arg is not None:
        actual_annotation = list[arg]  # type: ignore[valid-type]
    else:
        actual_annotation = list
    return mgw.ListEdit(
        label=p.name,
        annotation=actual_annotation,
        layout="vertical",
    )


def _make_generic(p: ParamDescription) -> mgw.Widget:
    """Return ``magicgui.create_widget``'s widget for any other annotation.

    Raises TypeError or ValueError if ``magicgui`` does not support it.
    """
    options: dict[str, Any] = {}
    # a parameter with no default gets magicgui's sentinel rather than None:
    # a widget that cannot hold None, such as the CheckBox built for a bool,
    # raises on being handed one
    return mgw.create_widget(
        annotation=p.annotation,
        name=p.name,
        param_kind=p.kind.name,
        value=p.default if p.has_default else Undefined,
        options=options,
    )


_WidgetPredicate: TypeAlias = Callable[[ParamDescription], bool]
_WidgetFactory: TypeAlias = Callable[[ParamDescription], mgw.Widget]

_WIDGET_FACTORY_MAP: list[tuple[_WidgetPredicate, _WidgetFactory]] = [
    (_is_hidden_or_action, _make_dummy),
    (_is_multiselect_device, _make_device_sequence_edit),
    (_is_singleselect_device, _make_singleselect_device),
    (_is_literal_choices, _make_literal_combobox),
    (_is_non_device_sequence, _make_list_edit),
    (_always, _make_generic),
]


def _try_factory_entry(
    predicate: _WidgetPredicate,
    factory: _WidgetFactory,
    param: ParamDescription,
) -> mgw.Widget | None:
    """Call the factory if the predicate matches.

    Only the predicate is guarded: a factory raising is a bug and propagates.
    """
    try:
        matched = predicate(param)
    except Exception:  # noqa: BLE001 - a failing predicate means "no match", never a crash
        return None
    if matched:
        return factory(param)
    return None


def create_param_widget(param: ParamDescription) -> mgw.Widget:
    """Create a ``magicgui`` widget for *param*.

    Parameters
    ----------
    param : ParamDescription
        The parameter specification.

    Returns
    -------
    mgw.Widget
        The created widget.

    Raises
    ------
    RuntimeError
        If every entry in ``_WIDGET_FACTORY_MAP`` fails.
    """
    for predicate, factory in _WIDGET_FACTORY_MAP:
        widget = _try_factory_entry(predicate, factory, param)
        if widget is not None:
            return widget
    raise RuntimeError(
        f"No widget factory matched parameter {param.name!r} "
        f"(annotation: {param.annotation!r}). "
        f"This is a bug - create_plan_spec should have caught this."
    )
