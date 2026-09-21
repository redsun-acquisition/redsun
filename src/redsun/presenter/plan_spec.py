"""Describe a plan's signature as a `PlanSpec`.

`create_plan_spec` inspects a ``bluesky`` ``MsgGenerator`` function and returns
a `PlanSpec` describing its parameters, from which a view builds a parameter
form.

`_ANN_HANDLER_MAP` lists ``(predicate, handler)`` pairs turning annotations into
`ParamDescription` fields (choices, ``device_proto``, ``multiselect``).
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
    TYPE_CHECKING,
    Annotated,
    Any,
    ForwardRef,
    Literal,
    NamedTuple,
    get_args,
    get_origin,
)

from ophyd_async.core import Device as OADevice
from typing_extensions import Format, evaluate_forward_ref, get_annotations

from redsun.engine.actions import Action
from redsun.presenter.utils import (
    get_choice_list,
    isdevice,
    isdevicesequence,
    isdeviceset,
    issequence,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class UnresolvableAnnotationError(TypeError):
    """Raised when a plan parameter's annotation maps to no widget.

    Parameters
    ----------
    plan_name : str
        Name of the plan.
    param_name : str
        Name of the parameter.
    annotation : Any
        The unresolvable annotation.
    """

    def __init__(self, plan_name: str, param_name: str, annotation: Any) -> None:
        self.plan_name = plan_name
        self.param_name = param_name
        self.annotation = annotation
        super().__init__(
            f"Plan {plan_name!r}: cannot resolve annotation for parameter "
            f"{param_name!r} ({annotation!r}). "
            f"A required parameter must be a Literal, a device protocol, a "
            f"sequence of them, a sequence of any other renderable type, or one "
            f"of int, float, str, bool, bytes, range, Path, an Enum or a "
            f"datetime type. The plan will be skipped."
        )


class ParamKind(IntEnum):
    """`inspect._ParameterKind` as a public `IntEnum`.

    Usable in ``match``/``case`` without importing private standard library
    names.
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
    """Description of one plan parameter."""

    name: str
    """Name of the parameter in the plan signature."""

    kind: ParamKind
    """Kind of the parameter, as `inspect.Parameter.kind`."""

    annotation: Any
    """Type annotation, without `Annotated` metadata."""

    default: Any
    """Default value of the parameter, or `inspect.Parameter.empty` if none."""

    choices: list[Any] | None = None
    """Selectable values: a `Literal`'s own values, or device names."""

    multiselect: bool = False
    """Whether several values can be selected, as for `Sequence[OADevice]`."""

    hidden: bool = False
    """Whether the parameter is hidden from the interface, as for metadata only."""

    actions: Sequence[Action] | Action | None = None
    """Actions taken from the parameter's default value, if any."""

    device_proto: type[Any] | None = None
    """Device class or runtime-checkable protocol of a device parameter, used to look devices up when resolving arguments."""

    @property
    def has_default(self) -> bool:
        """Return ``True`` if the parameter has a default."""
        return self.default is not _empty


@dataclass(eq=False)
class PlanSpec:
    """Description of a plan's signature and type hints."""

    name: str
    """Plan name, the callable's ``__name__``."""

    docs: str
    """Plan docstring, or a default message without one."""

    parameters: list[ParamDescription]
    """One description per parameter, in order."""

    togglable: bool = False
    """Whether the plan loops until stopped with a toggle button."""

    pausable: bool = False
    """Whether a running togglable plan can be paused and resumed."""


class _FieldsFromAnnotation(NamedTuple):
    """Fields an annotation handler returns.

    Fields irrelevant to an annotation keep their defaults (None / False).
    """

    choices: list[Any] | None = None
    multiselect: bool = False
    device_proto: type[Any] | None = None


def _handle_literal(
    ann: Any,
    _: cabc.Mapping[str, OADevice],
) -> _FieldsFromAnnotation:
    return _FieldsFromAnnotation(choices=list(get_args(ann)))


def _device_fields(
    proto: Any,
    devices: cabc.Mapping[str, OADevice],
    multiselect: bool,
) -> _FieldsFromAnnotation:
    """Offer the devices matching *proto* as choices, keyed by their name."""
    matching = [key for key, obj in devices.items() if isinstance(obj, proto)]
    if not matching:
        return _FieldsFromAnnotation()
    return _FieldsFromAnnotation(
        choices=matching,
        multiselect=multiselect,
        device_proto=proto,
    )


def _handle_device_collection(
    ann: Any,
    devices: cabc.Mapping[str, OADevice],
) -> _FieldsFromAnnotation:
    return _device_fields(get_args(ann)[0], devices, multiselect=True)


def _handle_device(
    ann: Any,
    devices: cabc.Mapping[str, OADevice],
) -> _FieldsFromAnnotation:
    return _device_fields(ann, devices, multiselect=False)


def _handle_var_positional_device(
    ann: Any,
    devices: cabc.Mapping[str, OADevice],
) -> _FieldsFromAnnotation:
    return _device_fields(ann, devices, multiselect=True)


_AnnHandler = cabc.Callable[[Any, cabc.Mapping[str, OADevice]], _FieldsFromAnnotation]
_AnnPredicate = cabc.Callable[[Any, ParamKind], bool]

#: ``(predicate, handler)`` pairs, tried in order; the first match wins.
_ANN_HANDLER_MAP: list[tuple[_AnnPredicate, _AnnHandler]] = [
    (
        # get_origin returns Literal at runtime, which mypy cannot prove
        lambda ann, _: get_origin(ann) is Literal,  # type: ignore[comparison-overlap]
        _handle_literal,
    ),
    (
        lambda ann, _: isdeviceset(ann),
        _handle_device_collection,
    ),
    (
        lambda ann, _: isdevicesequence(ann),
        _handle_device_collection,
    ),
    (
        lambda ann, kind: kind is ParamKind.VAR_POSITIONAL and isdevice(ann),
        _handle_var_positional_device,
    ),
    (
        lambda ann, _: isdevice(ann),
        _handle_device,
    ),
]


def _try_dispatch_entry(
    predicate: _AnnPredicate,
    handler: _AnnHandler,
    ann: Any,
    kind: ParamKind,
    devices: cabc.Mapping[str, OADevice],
) -> _FieldsFromAnnotation | None:
    """Try one ``(predicate, handler)`` entry; return ``None`` if it raises."""
    try:
        if predicate(ann, kind):
            return handler(ann, devices)
        return None
    except Exception:  # noqa: BLE001 - a failing predicate means "no match", never a crash
        return None


def _dispatch_annotation(
    ann: Any,
    kind: ParamKind,
    devices: cabc.Mapping[str, OADevice],
) -> _FieldsFromAnnotation:
    """Walk ``_ANN_HANDLER_MAP`` and call the first matching handler.

    An entry whose predicate or handler raises is skipped; an annotation no
    entry matches gives empty fields.
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

    Returns the ``Action``, or list of them, if the default holds actions, and
    ``None`` otherwise. Also checks the annotation is ``Action``,
    ``Sequence[Action]`` or a union containing ``Action``.

    Raises
    ------
    TypeError
        If the default holds actions but the annotation does not allow them.
    """
    if param.default is _empty:
        return None
    if isinstance(param.default, Action):
        actions_meta: Sequence[Action] | Action = param.default
    elif (
        param.default
        and isinstance(param.default, cabc.Sequence)
        and all(isinstance(a, Action) for a in param.default)
    ):
        actions_meta = list(param.default)
    else:
        return None

    origin = get_origin(ann)
    args = get_args(ann)
    is_action_type = _is_action_type(ann)
    is_sequence_action = (
        origin is not None
        # try/except because issubclass on Protocols can raise
        and _safe_issubclass(origin, cabc.Sequence)
        and bool(args)
        and _is_action_type(args[0])
    )
    is_union_containing_action = any(
        _is_action_type(arg) for arg in args if arg is not type(None)
    )

    if not (is_action_type or is_sequence_action or is_union_containing_action):
        raise TypeError(
            f"Parameter {param.name!r} has Action instances in its default value "
            f"but is not annotated as Action, Sequence[Action], or a union "
            f"containing Action; got {ann!r}"
        )
    return actions_meta


def _is_action_type(ann: Any) -> bool:
    """Whether *ann* is `Action` itself or a subclass of it."""
    return isinstance(ann, type) and issubclass(ann, Action)


def _safe_issubclass(cls: Any, parent: type) -> bool:
    """``issubclass`` returning ``False`` instead of raising ``TypeError``."""
    try:
        return issubclass(cls, parent)
    except TypeError:
        return False


def _iterate_signature(sig: inspect.Signature) -> cabc.Iterator[tuple[str, Parameter]]:
    """Iterate a signature's parameters, skipping ``self``/``cls``.

    Yields
    ------
    Iterator[tuple[str, Parameter]]
        (name, ``Parameter``) pairs.
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


_PRIMITIVE_TYPES: frozenset[type] = frozenset(
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


def _is_renderable(ann: Any) -> bool:
    """Return ``True`` if a view layer can be expected to build a control for *ann*.

    Imports no toolkit, so it can run before any application object exists.

    `Any` is excluded: it says nothing about the value, so no view can choose a
    control. Refusing here names the plan and parameter, which a failure while
    building the form would not.
    """
    if ann is Any:
        return False
    if ann in _PRIMITIVE_TYPES:
        return True
    if _safe_issubclass(ann, enum.Enum):
        return True
    # a sequence of anything but devices is an editable list of its element
    # type; a device sequence is handled by the dispatch table, which offers
    # the matching device names as choices instead
    return issequence(ann) and not isdevicesequence(ann) and not isdeviceset(ann)


def _resolve_annotations(
    func_obj: cabc.Callable[..., Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Resolve every annotation of *func_obj*, one at a time.

    Returns the annotations that evaluate, and the source text of those naming
    something missing at runtime. Resolving each separately keeps one missing
    name from hiding the others.
    """
    namespace = getattr(func_obj, "__globals__", None)
    resolved: dict[str, Any] = {}
    unresolved: dict[str, str] = {}
    for name, value in get_annotations(func_obj, format=Format.FORWARDREF).items():
        # a module without the annotations future import already evaluated
        # its annotations; only what is still text needs the namespace
        if isinstance(value, str):
            value = ForwardRef(value)
        if isinstance(value, ForwardRef):
            try:
                value = evaluate_forward_ref(value, globals=namespace)
            except NameError:
                unresolved[name] = value.__forward_arg__
                continue
        # get_type_hints substitutes NoneType, which the return-type
        # checks below rely on to tell "-> None" from "no annotation"
        resolved[name] = type(None) if value is None else value
    return resolved, unresolved


def create_plan_spec(
    plan: cabc.Callable[..., cabc.Generator[Any, Any, Any]],
    devices: cabc.Mapping[str, OADevice],
) -> PlanSpec:
    """Inspect *plan* and return a ``PlanSpec`` with one ``ParamDescription`` per parameter.

    Parameters
    ----------
    plan : Callable[..., Any]
        The plan function or bound method, a generator function annotated to
        return a ``MsgGenerator``.
    devices : Mapping[str, OADevice]
        The session's devices, giving ``choices`` for parameters annotated
        with an ``OADevice`` subtype.

    Returns
    -------
    PlanSpec
        The plan specification.

    Raises
    ------
    TypeError
        If *plan* is not a generator function or its return type is not a
        ``MsgGenerator`` (``Generator[Msg, Any, Any]``).
    UnresolvableAnnotationError
        If an annotation names something missing at runtime, or no view can
        build a control for it.
    RuntimeError
        On an unexpected ``inspect.Parameter.kind``.
    """
    func_obj: cabc.Callable[..., cabc.Generator[Any, Any, Any]] = getattr(
        plan, "__func__", plan
    )

    if not inspect.isgeneratorfunction(func_obj):
        raise TypeError(f"Plan {func_obj.__name__!r} must be a generator function.")

    sig = signature(func_obj)
    type_hints, unresolved = _resolve_annotations(func_obj)

    if "return" in unresolved:
        raise UnresolvableAnnotationError(
            func_obj.__name__, "return", unresolved["return"]
        )

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
        if name in unresolved:
            raise UnresolvableAnnotationError(func_obj.__name__, name, unresolved[name])

        raw_ann: Any = type_hints.get(name, param.annotation)
        if raw_ann is _empty:
            raw_ann = Any

        if get_origin(raw_ann) is Annotated:
            ann_args = get_args(raw_ann)
            ann: Any = ann_args[0] if ann_args else Any
        else:
            ann = raw_ann

        actions_meta = _extract_action_meta(param, ann)

        pkind = _PARAM_KIND_MAP.get(param.kind)
        if pkind is None:
            raise RuntimeError(f"Unexpected parameter kind: {param.kind!r}")

        # Action parameters never get a widget, so they skip dispatch
        if actions_meta is not None:
            fields = _FieldsFromAnnotation()
        else:
            fields = _dispatch_annotation(ann, pkind, devices)

        # refuse now: failing here is clearer than a broken control or a
        # crash once the plan runs
        is_required = param.default is _empty
        needs_control = (
            actions_meta is None
            and is_required
            and pkind is not ParamKind.VAR_KEYWORD
            and fields.choices is None
        )
        if needs_control and not _is_renderable(ann):
            raise UnresolvableAnnotationError(func_obj.__name__, name, ann)

        params.append(
            ParamDescription(
                name=name,
                kind=pkind,
                annotation=ann,
                default=param.default,
                choices=fields.choices,
                multiselect=fields.multiselect,
                actions=actions_meta,
                device_proto=fields.device_proto,
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
    """Build the ``(args, kwargs)`` calling a plan, from its ``PlanSpec``.

    Parameters
    ----------
    spec : PlanSpec
        The plan specification.
    values : Mapping[str, Any]
        Resolved values by parameter name.

    Returns
    -------
    tuple[tuple[Any, ...], dict[str, Any]]
        Positional and keyword arguments for the plan.

    Notes
    -----
    * ``POSITIONAL_ONLY`` and ``POSITIONAL_OR_KEYWORD`` -> ``args``, in
      declaration order.
    * ``KEYWORD_ONLY`` -> ``kwargs``.
    * ``VAR_POSITIONAL`` (``*args``) -> sequence expanded into ``args``.
    * ``VAR_KEYWORD`` (``**kwargs``) -> mapping merged into ``kwargs``.
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
    devices: Mapping[str, OADevice],
) -> dict[str, Any]:
    """Turn parameter values from the interface into values a plan takes.

    * **Action parameters** are filled from the spec when the interface lacks
      them.
    * **Device parameters**: names become ``OADevice`` instances from
      ``devices``.
    * **Everything else** passes unchanged.

    Parameters
    ----------
    spec : PlanSpec
        The plan specification.
    param_values : Mapping[str, Any]
        Parameter values from the interface.
    devices : Mapping[str, OADevice]
        The session's devices.

    Returns
    -------
    dict[str, Any]
        Resolved arguments for ``collect_arguments``.
    """
    values: dict[str, Any] = dict(param_values)

    # action parameters have no widget, so their values never come from the UI
    for p in spec.parameters:
        if p.actions is not None and p.name not in values:
            values[p.name] = p.actions

    resolved: dict[str, Any] = {}

    for p in spec.parameters:
        if p.name not in values:
            continue
        val = values[p.name]

        if p.choices is not None and p.device_proto is not None:
            if isinstance(val, str):
                labels = [val]
            elif isinstance(val, (cabc.Sequence, cabc.Set)) and not isinstance(
                val, (str, bytes)
            ):
                labels = [str(v) for v in val]
            else:
                labels = [str(val)]

            device_list = get_choice_list(devices, p.device_proto, labels)

            if p.kind is ParamKind.VAR_POSITIONAL or isdevicesequence(p.annotation):
                resolved[p.name] = device_list
            elif isdeviceset(p.annotation):
                resolved[p.name] = set(device_list)
            else:
                resolved[p.name] = device_list[0] if device_list else None
        else:
            resolved[p.name] = val

    return resolved
