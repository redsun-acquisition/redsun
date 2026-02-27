"""Plan specification: inspect a plan's signature into a structured `PlanSpec`.

This module provides `create_plan_spec`, which inspects a Bluesky
``MsgGenerator`` function and returns a `PlanSpec` — a structured
description of the plan's parameters that the view layer can use to
automatically generate a parameter form.

The annotation dispatch system is table-driven: `_ANN_HANDLER_MAP` maps
``(predicate, handler)`` pairs that convert raw type annotations into
`ParamDescription` fields (choices, device_proto, multiselect).
"""

from __future__ import annotations

import collections.abc as cabc
import datetime
import enum
import inspect
from dataclasses import dataclass
from enum import IntEnum
from inspect import Parameter, _empty, signature
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Mapping,
    NamedTuple,
    Sequence,
    get_args,
    get_origin,
    get_type_hints,
)

from beartype.door import LiteralTypeHint, TypeHint

from redsun.device import PDevice
from redsun.engine.actions import Action
from redsun.presenter.utils import get_choice_list, isdevice, isdeviceset, isdevicesequence


class UnresolvableAnnotationError(TypeError):
    """Raised when a plan parameter's annotation cannot be mapped to a widget.

    Parameters
    ----------
    plan_name : str
        Name of the plan that contains the unresolvable parameter.
    param_name : str
        Name of the parameter whose annotation could not be resolved.
    annotation : Any
        The annotation that could not be resolved.
    """

    def __init__(self, plan_name: str, param_name: str, annotation: Any) -> None:
        self.plan_name = plan_name
        self.param_name = param_name
        self.annotation = annotation
        super().__init__(
            f"Plan {plan_name!r}: cannot resolve annotation for parameter "
            f"{param_name!r} ({annotation!r}). "
            f"Supported types are: Literal, PDevice subtype, Sequence[PDevice], "
            f"Path, and magicgui-supported primitives (int, float, str, bool, …). "
            f"The plan will be skipped."
        )


class ParamKind(IntEnum):
    """Public mirror of `inspect._ParameterKind` as a stable `IntEnum`.

    Using a dedicated enum keeps the public API stable and allows use in
    ``match``/``case`` statements without importing private stdlib symbols.
    """

    POSITIONAL_ONLY = 0
    POSITIONAL_OR_KEYWORD = 1
    VAR_POSITIONAL = 2
    KEYWORD_ONLY = 3
    VAR_KEYWORD = 4


# Mapping from inspect.Parameter.kind to our ParamKind
_PARAM_KIND_MAP: dict[Any, ParamKind] = {
    Parameter.POSITIONAL_ONLY: ParamKind.POSITIONAL_ONLY,
    Parameter.POSITIONAL_OR_KEYWORD: ParamKind.POSITIONAL_OR_KEYWORD,
    Parameter.VAR_POSITIONAL: ParamKind.VAR_POSITIONAL,
    Parameter.KEYWORD_ONLY: ParamKind.KEYWORD_ONLY,
    Parameter.VAR_KEYWORD: ParamKind.VAR_KEYWORD,
}


@dataclass
class ParamDescription:
    """Description of a single plan parameter."""

    name: str
    """Name of the parameter, as declared in the plan signature."""

    kind: ParamKind
    """Kind of the parameter, mirroring `inspect.Parameter.kind`."""

    annotation: Any
    """Unwrapped type annotation; `Annotated` metadata has been stripped."""

    default: Any
    """Default value of the parameter, or `inspect.Parameter.empty` if none."""

    choices: list[str] | None = None
    """String labels for selectable values; used for `Literal` and `PDevice`-backed parameters."""

    multiselect: bool = False
    """Whether the parameter allows multiple simultaneous selections (e.g. for `Sequence[PDevice]`)."""

    hidden: bool = False
    """Whether this parameter should be hidden from the UI (e.g. because it's only for metadata, not user input)."""

    actions: Sequence[Action] | Action | None = None
    """Action metadata extracted from the parameter's default value, if any."""

    is_device_set: bool = False
    """Whether the annotation is a set-like collection (``Set[PDevice]``) rather than a sequence.
    Affects how resolved values are coerced before being passed to the plan."""

    device_proto: type[PDevice] | None = None
    """The `PDevice` protocol/class for model-backed parameters, if any; used for device look-up during argument resolution."""

    @property
    def has_default(self) -> bool:
        """Return ``True`` if this parameter carries a default value."""
        return self.default is not _empty


@dataclass(eq=False)
class PlanSpec:
    """Structured description of a plan's signature and type hints."""

    name: str
    """Plan name (``__name__`` of the underlying callable)."""

    docs: str
    """Plan docstring, or a default message if no docstring is available."""

    parameters: list[ParamDescription]
    """Ordered list of parameter descriptions, one per plan parameter."""

    togglable: bool = False
    """Whether the plan runs as an infinite loop that can be stopped via a toggle button."""

    pausable: bool = False
    """Whether a running togglable plan can be paused and resumed."""


class _FieldsFromAnnotation(NamedTuple):
    """Structured result returned by each annotation handler.

    Fields not relevant to a particular annotation shape should be left
    at their defaults (None / False).
    """

    choices: list[str] | None = None
    multiselect: bool = False
    is_device_set: bool = False
    device_proto: type[PDevice] | None = None


def _handle_literal(
    ann: Any,
    _: cabc.Mapping[str, PDevice],
) -> _FieldsFromAnnotation:
    th = TypeHint(ann)
    choices = [str(a) for a in th.args]
    return _FieldsFromAnnotation(choices=choices)


def _handle_device_sequence(
    ann: Any,
    devices: cabc.Mapping[str, PDevice],
) -> _FieldsFromAnnotation:
    elem_ann: Any = get_args(ann)[0]
    matching = [key for key, obj in devices.items() if isinstance(obj, elem_ann)]
    if not matching:
        return _FieldsFromAnnotation()
    return _FieldsFromAnnotation(
        choices=matching,
        multiselect=True,
        device_proto=elem_ann,
    )


def _handle_device_set(
    ann: Any,
    devices: cabc.Mapping[str, PDevice],
) -> _FieldsFromAnnotation:
    elem_ann: Any = get_args(ann)[0]
    matching = [key for key, obj in devices.items() if isinstance(obj, elem_ann)]
    if not matching:
        return _FieldsFromAnnotation()
    return _FieldsFromAnnotation(
        choices=matching,
        multiselect=True,
        is_device_set=True,
        device_proto=elem_ann,
    )


def _handle_device(
    ann: Any,
    devices: cabc.Mapping[str, PDevice],
) -> _FieldsFromAnnotation:
    matching = [key for key, obj in devices.items() if isinstance(obj, ann)]
    if not matching:
        return _FieldsFromAnnotation()
    return _FieldsFromAnnotation(
        choices=matching,
        multiselect=False,
        device_proto=ann,
    )


def _handle_var_positional_device(
    ann: Any,
    devices: cabc.Mapping[str, PDevice],
) -> _FieldsFromAnnotation:
    matching = [key for key, obj in devices.items() if isinstance(obj, ann)]
    if not matching:
        return _FieldsFromAnnotation()
    return _FieldsFromAnnotation(
        choices=matching,
        multiselect=True,
        device_proto=ann,
    )


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------
# Each entry is (predicate, handler).
# Predicates: (annotation, ParamKind) -> bool
# Handlers:   (annotation, devices)    -> _FieldsFromAnnotation
#
# Entries are checked in order; the first matching handler is called.
# To support a new annotation shape: insert a (predicate, handler) pair
# at the appropriate priority. Nothing else needs to change.
# ---------------------------------------------------------------------------

_AnnHandler = cabc.Callable[[Any, cabc.Mapping[str, PDevice]], _FieldsFromAnnotation]
_AnnPredicate = cabc.Callable[[Any, ParamKind], bool]

_ANN_HANDLER_MAP: list[tuple[_AnnPredicate, _AnnHandler]] = [
    # 1. Literal[...] → fixed string choices (no model look-up)
    (
        lambda ann, _: isinstance(TypeHint(ann), LiteralTypeHint),
        _handle_literal,
    ),
    # 2. Set[PDevice] / AbstractSet[PDevice] / FrozenSet[PDevice] → multi-select (set semantics)
    (
        lambda ann, _: isdeviceset(ann),
        _handle_device_set,
    ),
    # 3. Sequence[PDevice] → multi-select device widget
    (
        lambda ann, _: isdevicesequence(ann),
        _handle_device_sequence,
    ),
    # 4. *args: PDevice  (VAR_POSITIONAL + bare device type) → multi-select
    (
        lambda ann, kind: kind is ParamKind.VAR_POSITIONAL and isdevice(ann),
        _handle_var_positional_device,
    ),
    # 5. Bare PDevice type → single-select device widget
    (
        lambda ann, _: isdevice(ann),
        _handle_device,
    ),
    # 6. Catch-all fallback → no choices, no model
    (
        lambda ann, kind: True,
        lambda ann, devices: _FieldsFromAnnotation(),
    ),
]


def _try_dispatch_entry(
    predicate: _AnnPredicate,
    handler: _AnnHandler,
    ann: Any,
    kind: ParamKind,
    devices: cabc.Mapping[str, PDevice],
) -> _FieldsFromAnnotation | None:
    """Attempt one ``(predicate, handler)`` entry; return ``None`` on any exception.

    Isolating the try/except here keeps it out of the ``for`` loop body in
    ``_dispatch_annotation``, satisfying ruff's PERF203 rule without
    suppressing it via ``noqa``.
    """
    try:
        if predicate(ann, kind):
            return handler(ann, devices)
        return None
    except Exception:
        return None


def _dispatch_annotation(
    ann: Any,
    kind: ParamKind,
    devices: cabc.Mapping[str, PDevice],
) -> _FieldsFromAnnotation:
    """Walk ``_ANN_HANDLER_MAP`` and call the first matching handler.

    If a predicate or handler raises (e.g. beartype cannot handle an exotic
    annotation), that entry is skipped and the next one is tried.
    """
    for predicate, handler in _ANN_HANDLER_MAP:
        result = _try_dispatch_entry(predicate, handler, ann, kind, devices)
        if result is not None:
            return result
    return _FieldsFromAnnotation()


def _extract_action_meta(
    param: Parameter,
    ann: Any,
) -> Sequence[Action] | Action | None:
    """Extract ``Action`` instances from a parameter's default value.

    Returns the ``Action`` (or list of ``Action``) if the default value is
    action metadata, ``None`` otherwise.  Also validates that the annotation
    is compatible (``Action``, ``Sequence[Action]``, or a union containing
    ``Action``).

    Raises
    ------
    TypeError
        If the default contains ``Action`` instances but the annotation is
        incompatible.
    """
    if param.default is _empty:
        return None
    if isinstance(param.default, Action):
        actions_meta: Sequence[Action] | Action = param.default
    elif isinstance(param.default, cabc.Sequence) and all(
        isinstance(a, Action) for a in param.default
    ):
        actions_meta = list(param.default)
    else:
        return None

    # Validate annotation compatibility
    origin = get_origin(ann)
    is_action_type = ann is Action or (
        isinstance(ann, type) and issubclass(ann, Action)
    )
    is_sequence_action = (
        origin is not None
        and (
            # try/except because issubclass on Protocols can raise
            _safe_issubclass(origin, cabc.Sequence)
        )
        and bool(get_args(ann))
        and (
            get_args(ann)[0] is Action
            or (
                isinstance(get_args(ann)[0], type)
                and issubclass(get_args(ann)[0], Action)
            )
        )
    )
    is_union_containing_action = any(
        arg is Action or (isinstance(arg, type) and issubclass(arg, Action))
        for arg in get_args(ann)
        if arg is not type(None)
    )

    if not (is_action_type or is_sequence_action or is_union_containing_action):
        raise TypeError(
            f"Parameter {param.name!r} has Action instances in its default value "
            f"but is not annotated as Action, Sequence[Action], or a union "
            f"containing Action; got {ann!r}"
        )
    return actions_meta


def _safe_issubclass(cls: Any, parent: type) -> bool:
    """``issubclass`` wrapper that returns ``False`` on ``TypeError``."""
    try:
        return issubclass(cls, parent)
    except TypeError:
        return False


def _iterate_signature(sig: inspect.Signature) -> cabc.Iterator[tuple[str, Parameter]]:
    """Iterate over a function signature's parameters, skipping ``self``/``cls``.

    Yields
    ------
    Iterator[tuple[str, Parameter]]
        Tuples of (parameter name, ``Parameter`` object).
    """
    items = list(sig.parameters.items())
    if items:
        first_name, first_param = items[0]
        if first_name in {"self", "cls"} and first_param.kind in (
            Parameter.POSITIONAL_ONLY,
            Parameter.POSITIONAL_OR_KEYWORD,
        ):
            items = items[1:]
    yield from items


_MAGICGUI_NATIVE_TYPES: frozenset[type] = frozenset(
    {
        int,
        float,
        str,
        bool,
        bytes,
        range,
        datetime.datetime,
        datetime.date,
        datetime.time,
        datetime.timedelta,
        Path,
    }
)


def _is_magicgui_resolvable(ann: Any) -> bool:
    """Return ``True`` if *ann* is known to produce a real widget via magicgui.

    This is a pure-Python check with no Qt dependency, safe to call at plan
    construction time before a ``QApplication`` exists.

    We do **not** include `Any` in the resolvable set, because magicgui
    silently produces a ``LineEdit`` for it — the same opaque behaviour we
    are trying to eliminate.
    """
    if ann is Any:
        return False
    if ann in _MAGICGUI_NATIVE_TYPES:
        return True
    # Enum subclasses produce a ComboBox in magicgui
    try:
        return isinstance(ann, type) and issubclass(ann, enum.Enum)
    except TypeError:
        return False


def create_plan_spec(
    plan: cabc.Callable[..., cabc.Generator[Any, Any, Any]],
    devices: cabc.Mapping[str, PDevice],
) -> PlanSpec:
    """Inspect *plan* and return a ``PlanSpec`` with one ``ParamDescription`` per parameter.

    Parameters
    ----------
    plan : Callable[..., Any]
        The plan function (or bound method) to inspect.
        Must be a generator function whose return annotation is a ``MsgGenerator``.
    devices : Mapping[str, PDevice]
        Registry of active devices; used to compute ``choices`` for parameters
        annotated with a ``PDevice`` subtype.

    Returns
    -------
    PlanSpec
        Fully populated plan specification.

    Raises
    ------
    TypeError
        If *plan* is not a generator function or its return type is not a
        ``MsgGenerator`` (``Generator[Msg, Any, Any]``).
    RuntimeError
        If an unexpected ``inspect.Parameter.kind`` is encountered.
    """
    func_obj: cabc.Callable[..., cabc.Generator[Any, Any, Any]] = getattr(
        plan, "__func__", plan
    )

    if not inspect.isgeneratorfunction(func_obj):
        raise TypeError(f"Plan {func_obj.__name__!r} must be a generator function.")

    sig = signature(func_obj)
    type_hints = get_type_hints(func_obj, include_extras=True)
    return_type = type_hints.get("return", None)

    if return_type is None:
        raise TypeError(
            f"Plan {func_obj.__name__!r} must have a return type annotation."
        )

    ret_origin = get_origin(return_type)
    is_generator = ret_origin is not None and _safe_issubclass(
        ret_origin, cabc.Generator
    )
    if not is_generator:
        raise TypeError(
            f"Plan {func_obj.__name__!r} must have a MsgGenerator return type; "
            f"got {return_type!r}."
        )

    params: list[ParamDescription] = []

    for name, param in _iterate_signature(sig):
        # Resolve the raw annotation, stripping Annotated[T, ...] → T
        raw_ann: Any = type_hints.get(name, param.annotation)
        if raw_ann is _empty:
            raw_ann = Any

        if get_origin(raw_ann) is Annotated:
            ann_args = get_args(raw_ann)
            ann: Any = ann_args[0] if ann_args else Any
        else:
            ann = raw_ann

        # Extract Action metadata (validated against the annotation)
        actions_meta = _extract_action_meta(param, ann)

        # Map inspect kind -> our ParamKind
        pkind = _PARAM_KIND_MAP.get(param.kind)
        if pkind is None:
            raise RuntimeError(f"Unexpected parameter kind: {param.kind!r}")

        # Dispatch annotation -> choices / device_proto / multiselect
        # (skip for Action parameters — they get no normal widget)
        if actions_meta is not None:
            fields = _FieldsFromAnnotation()
        else:
            fields = _dispatch_annotation(ann, pkind, devices)

        # Reject unresolvable required parameters
        # If dispatch produced no choices and no device_proto, the param
        # will fall through to the magicgui generic path at widget-creation
        # time. Probe that path now so we can fail fast here with a clear
        # error, rather than silently producing a broken LineEdit widget or
        # crashing later during plan execution.
        #
        # Parameters that are exempt from this check:
        # - Action params: never get a widget
        # - VAR_KEYWORD (**kwargs): no generic widget is ever built
        # - Params with a dispatch hit (choices set): already handled
        # - Params with a default: the default will be used if the widget
        #   can't be built, so the plan can still run
        # -----------------------------------------------------------------
        is_required = param.default is _empty
        needs_widget_probe = (
            actions_meta is None
            and is_required
            and pkind is not ParamKind.VAR_KEYWORD
            and fields.choices is None
        )
        if needs_widget_probe and not _is_magicgui_resolvable(ann):
            raise UnresolvableAnnotationError(func_obj.__name__, name, ann)

        params.append(
            ParamDescription(
                name=name,
                kind=pkind,
                annotation=ann,
                default=param.default,
                choices=fields.choices,
                multiselect=fields.multiselect,
                is_device_set=fields.is_device_set,
                actions=actions_meta,
                device_proto=fields.device_proto,
                hidden=False,
            )
        )

    togglable = bool(getattr(func_obj, "__togglable__", False))
    pausable = bool(getattr(func_obj, "__pausable__", False))

    return PlanSpec(
        name=func_obj.__name__,
        docs=inspect.getdoc(func_obj) or "No documentation available.",
        parameters=params,
        togglable=togglable,
        pausable=pausable,
    )


def collect_arguments(
    spec: PlanSpec,
    values: cabc.Mapping[str, Any],
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Build ``(args, kwargs)`` for calling a plan, driven by a ``PlanSpec``.

    Parameters
    ----------
    spec : PlanSpec
        The plan specification.
    values : Mapping[str, Any]
        Mapping of parameter names to their resolved values.

    Returns
    -------
    tuple[tuple[Any, ...], dict[str, Any]]
        Positional and keyword arguments ready to be splatted into the plan.

    Notes
    -----
    * ``POSITIONAL_ONLY`` and ``POSITIONAL_OR_KEYWORD`` → go into ``args`` in
      declaration order.
    * ``KEYWORD_ONLY`` → go into ``kwargs``.
    * ``VAR_POSITIONAL`` (``*args``) → sequence is expanded into ``args``.
    * ``VAR_KEYWORD`` (``**kwargs``) → mapping is merged into ``kwargs``.
    """
    args: list[Any] = []
    kwargs: dict[str, Any] = {}

    for p in spec.parameters:
        if p.name not in values:
            continue
        value = values[p.name]

        match p.kind:
            case ParamKind.VAR_POSITIONAL:
                if isinstance(value, cabc.Sequence) and not isinstance(
                    value, (str, bytes)
                ):
                    args.extend(value)
                else:
                    args.append(value)
            case ParamKind.VAR_KEYWORD:
                if isinstance(value, cabc.Mapping):
                    kwargs.update(value)
                else:
                    raise TypeError(
                        f"Value for **{p.name} must be a Mapping, got {type(value)!r}"
                    )
            case ParamKind.POSITIONAL_ONLY | ParamKind.POSITIONAL_OR_KEYWORD:
                args.append(value)
            case ParamKind.KEYWORD_ONLY:
                kwargs[p.name] = value

    return tuple(args), kwargs


def resolve_arguments(
    spec: PlanSpec,
    param_values: Mapping[str, Any],
    devices: Mapping[str, PDevice],
) -> dict[str, Any]:
    """Resolve raw UI parameter values into plan-callable values.

    Handles:
    * **Action parameters** — injected from metadata when absent from the UI.
    * **Model-backed parameters** — string labels are resolved to live
      ``PDevice`` instances via the ``devices`` registry.
    * **Everything else** — passed through unchanged.

    Parameters
    ----------
    spec : PlanSpec
        The plan specification containing parameter metadata.
    param_values : Mapping[str, Any]
        Raw parameter values from the UI.
    devices : Mapping[str, PDevice]
        Active device registry.

    Returns
    -------
    dict[str, Any]
        Resolved arguments ready for ``collect_arguments``.
    """
    values: dict[str, Any] = dict(param_values)

    # Inject Action metadata for parameters that have no UI widget
    for p in spec.parameters:
        if p.actions is not None and p.name not in values:
            values[p.name] = p.actions

    resolved: dict[str, Any] = {}

    for p in spec.parameters:
        if p.name not in values:
            continue
        val = values[p.name]

        if p.choices is not None and p.device_proto is not None:
            # Coerce widget value (string, sequence, or set of strings) → list of labels
            if isinstance(val, str):
                labels = [val]
            elif isinstance(val, (cabc.Sequence, cabc.Set)) and not isinstance(val, (str, bytes)):
                labels = [str(v) for v in val]
            else:
                labels = [str(val)]

            device_list = get_choice_list(devices, p.device_proto, labels)

            if p.is_device_set:
                resolved[p.name] = set(device_list)
            elif p.kind is ParamKind.VAR_POSITIONAL or isdevicesequence(p.annotation):
                resolved[p.name] = device_list
            else:
                resolved[p.name] = device_list[0] if device_list else None
        else:
            resolved[p.name] = val

    return resolved
