"""Widget factory for plan parameter forms.

Maps a `ParamDescription` to an appropriate magicgui widget via a
table-driven factory registry (`_WIDGET_FACTORY_MAP`).

`create_param_widget` is the public entry point.  It walks
`_WIDGET_FACTORY_MAP` — an ordered list of ``(predicate, factory)``
pairs — and calls the first factory whose predicate matches the given
`ParamDescription`.

Extending the system
--------------------
To add support for a new annotation shape, define a predicate and a
factory function and insert a ``(predicate, factory)`` tuple at the
right priority position in `_WIDGET_FACTORY_MAP`.  Nothing else needs
to change.

Unresolvable annotations
------------------------
`create_plan_spec` pre-validates that every required parameter can be
mapped to a widget.  Plans with unresolvable required parameters raise
`UnresolvableAnnotationError` and are skipped by the presenter.
`create_param_widget` therefore raises `RuntimeError` (not a silent
fallback) if all factory entries fail.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeAlias, get_args

from magicgui import widgets as mgw

from redsun.presenter.plan_spec import ParamDescription, ParamKind
from redsun.presenter.utils import isdevice, isdevicesequence, issequence

if TYPE_CHECKING:
    from qtpy import QtWidgets


def _is_hidden_or_action(p: ParamDescription) -> bool:
    """Return true for parameters that should not get a normal input widget."""
    return p.actions is not None or p.hidden


def _is_multiselect_device(p: ParamDescription) -> bool:
    """Return true for Sequence[PDevice] or variadic *args: PDevice parameters."""
    if p.choices is None:
        return False
    is_ann_model_seq = isdevicesequence(p.annotation)
    is_var_model = p.kind is ParamKind.VAR_POSITIONAL and isdevice(p.annotation)
    return is_ann_model_seq or is_var_model


def _is_singleselect_device(p: ParamDescription) -> bool:
    """Return true for single PDevice parameters with a choices list."""
    return p.choices is not None and isdevice(p.annotation)


def _is_literal_choices(p: ParamDescription) -> bool:
    """Return true for parameters whose choices come from a Literal annotation."""
    return (
        p.choices is not None
        and not isdevice(p.annotation)
        and not isdevicesequence(p.annotation)
    )


def _is_non_device_sequence(p: ParamDescription) -> bool:
    """Return true for Sequence[T] parameters where T is not a PDevice type."""
    return (
        issequence(p.annotation)
        and not isdevicesequence(p.annotation)
        and not isinstance(p.annotation, (str, bytes))
    )


def _always(p: ParamDescription) -> bool:
    """Catch-all predicate — always matches."""
    return True


def _make_dummy(p: ParamDescription) -> mgw.Widget:
    """Return a read-only LineEdit placeholder for hidden/action params."""
    return mgw.LineEdit(name=p.name)


def _make_multiselect(p: ParamDescription) -> mgw.Widget:
    """Select widget allowing multiple device selections."""
    assert p.choices is not None
    w = mgw.Select(
        name=p.name,
        choices=p.choices,
        allow_multiple=True,
        annotation=p.annotation,
        value=p.default if p.has_default else p.choices[0],
    )
    inner: QtWidgets.QListWidget = w.native
    inner.setFixedWidth(inner.sizeHintForColumn(0) + inner.frameWidth() * 2 + 5)
    return w


def _make_singleselect_device(p: ParamDescription) -> mgw.Widget:
    """ComboBox widget for single PDevice selection."""
    assert p.choices is not None
    return mgw.ComboBox(
        name=p.name,
        choices=p.choices,
        value=p.default if p.has_default else p.choices[0],
    )


def _make_literal_combobox(p: ParamDescription) -> mgw.Widget:
    """ComboBox widget for Literal[...] choices."""
    assert p.choices is not None
    return mgw.ComboBox(
        name=p.name,
        choices=p.choices,
        value=p.default if p.has_default else p.choices[0],
    )


def _make_list_edit(p: ParamDescription) -> mgw.Widget:
    """ListEdit widget for non-device Sequence[T] parameters."""
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
    """Delegate to magicgui.create_widget for all other annotation types.

    Raises TypeError or ValueError if magicgui does not support the annotation.
    """
    options: dict[str, Any] = {}
    return mgw.create_widget(
        annotation=p.annotation,
        name=p.name,
        param_kind=p.kind.name,
        value=p.default if p.has_default else None,
        options=options,
    )


_WidgetPredicate: TypeAlias = Callable[[ParamDescription], bool]
_WidgetFactory: TypeAlias = Callable[[ParamDescription], mgw.Widget]

_WIDGET_FACTORY_MAP: list[tuple[_WidgetPredicate, _WidgetFactory]] = [
    (_is_hidden_or_action, _make_dummy),
    (_is_multiselect_device, _make_multiselect),
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
    """Attempt one (predicate, factory) entry; return None on any exception."""
    try:
        if predicate(param):
            return factory(param)
        return None
    except Exception:
        return None


def create_param_widget(param: ParamDescription) -> mgw.Widget:
    """Create a magicgui widget for *param* via the factory registry.

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
        f"This is a bug — create_plan_spec should have caught this."
    )
