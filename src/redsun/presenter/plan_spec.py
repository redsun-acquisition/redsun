"""Describe a plan's signature as a `PlanSpec`.

`create_plan_spec` inspects a `bluesky` `MsgGenerator` function and returns
a `PlanSpec` describing its parameters, from which a view builds the controls
of the plan.

`_fields_from_annotation` turns a `Literal` or device annotation into
`ParamDescription` fields (choices, `device_proto`, `multiselect`).
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
from types import NoneType
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

from typing_extensions import Format, evaluate_forward_ref, get_annotations

from redsun.engine.actions import PlanAction
from redsun.presenter.utils import (
    device_class,
    get_choice_list,
    isdevice,
    isdevicesequence,
    isdeviceset,
)

from ._shapes import (
    container_type,
    is_fixed_tuple,
    is_mapping,
    safe_issubclass,
    union_members,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ophyd_async.core import Device as OADevice


class UnresolvableAnnotationError(TypeError):
    """Raised when a plan parameter's annotation maps to no widget.

    Parameters
    ----------
    plan_name
        Name of the plan.
    param_name
        Name of the parameter.
    annotation
        The unresolvable annotation.
    """

    def __init__(self, plan_name: str, param_name: str, annotation: Any) -> None:
        self.plan_name = plan_name
        self.param_name = param_name
        self.annotation = annotation
        super().__init__(
            f"Plan {plan_name!r}: cannot resolve annotation for parameter "
            f"{param_name!r} ({annotation!r}). "
            f"A required parameter must be a device protocol, a sequence or set "
            f"of devices, one of int, float, str, bool, bytes, range, Path, a "
            f"Literal, an Enum or a datetime type, or a list, set, tuple, "
            f"mapping, union or optional of those."
        )


class ParamKind(IntEnum):
    """`inspect._ParameterKind` as a public `IntEnum`.

    Usable in `match`/`case` without importing private standard library
    names.
    """

    POSITIONAL_ONLY = 0
    """Given by position only."""

    POSITIONAL_OR_KEYWORD = 1
    """Given by position or by name."""

    VAR_POSITIONAL = 2
    """Any number of values given by position, as `*args`."""

    KEYWORD_ONLY = 3
    """Given by name only."""

    VAR_KEYWORD = 4
    """Any number of values given by name, as `**kwargs`."""


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
    """Whether no input can show the parameter, so a view leaves it out and the plan keeps its default."""

    actions: Sequence[PlanAction] | PlanAction | None = None
    """Actions taken from the parameter's default value, if any."""

    device_proto: type[Any] | None = None
    """Device class or runtime-checkable protocol of a device parameter, used to look devices up when resolving arguments."""

    @property
    def has_default(self) -> bool:
        """Return `True` if the parameter has a default."""
        return self.default is not _empty


@dataclass(eq=False)
class PlanSpec:
    """Description of a plan's signature and type hints."""

    name: str
    """Plan name, the callable's `__name__`."""

    docs: str
    """Plan docstring, or a default message without one."""

    parameters: list[ParamDescription]
    """One description per parameter, in order."""

    continuous: bool = False
    """Whether the plan loops until stopped with a toggle button."""

    pausable: bool = False
    """Whether a running continuous plan can be paused and resumed."""


class _FieldsFromAnnotation(NamedTuple):
    """Fields an annotation handler returns.

    Fields irrelevant to an annotation keep their defaults (None / False).
    """

    choices: list[Any] | None = None
    multiselect: bool = False
    device_proto: type[Any] | None = None


def _fields_from_annotation(
    ann: Any,
    kind: ParamKind,
    devices: cabc.Mapping[str, OADevice],
) -> _FieldsFromAnnotation:
    """Return the choices a `Literal` or device annotation offers.

    A device annotation offers the names of the devices matching it. Any other
    annotation, one no device matches, or one that raises while inspected
    gives empty fields.
    """
    try:
        if get_origin(ann) is Literal:
            return _FieldsFromAnnotation(choices=list(get_args(ann)))
        if isdeviceset(ann) or isdevicesequence(ann):
            proto, multiselect = device_class(get_args(ann)[0]), True
        elif isdevice(ann):
            proto, multiselect = device_class(ann), kind is ParamKind.VAR_POSITIONAL
        else:
            return _FieldsFromAnnotation()
        matching = [key for key, obj in devices.items() if isinstance(obj, proto)]
    except Exception:  # noqa: BLE001 - an annotation that cannot be inspected offers no choices, never a crash
        return _FieldsFromAnnotation()
    if not matching:
        return _FieldsFromAnnotation()
    return _FieldsFromAnnotation(
        choices=matching, multiselect=multiselect, device_proto=proto
    )


def _extract_action_meta(
    param: Parameter,
    ann: Any,
) -> Sequence[PlanAction] | PlanAction | None:
    """Extract `PlanAction` instances from a parameter's default value.

    Returns the `PlanAction`, or list of them, if the default holds actions, and
    `None` otherwise. Also checks the annotation is `PlanAction`,
    `Sequence[PlanAction]` or a union containing `PlanAction`.

    Raises
    ------
    TypeError
        If the default holds actions but the annotation does not allow them.
    """
    if param.default is _empty:
        return None
    if isinstance(param.default, PlanAction):
        actions_meta: Sequence[PlanAction] | PlanAction = param.default
    elif (
        param.default
        and isinstance(param.default, cabc.Sequence)
        and all(isinstance(a, PlanAction) for a in param.default)
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
        and safe_issubclass(origin, cabc.Sequence)
        and bool(args)
        and _is_action_type(args[0])
    )
    is_union_containing_action = any(
        _is_action_type(arg) for arg in args if arg is not type(None)
    )

    if not (is_action_type or is_sequence_action or is_union_containing_action):
        raise TypeError(
            f"Parameter {param.name!r} has PlanAction instances in its default value "
            f"but is not annotated as PlanAction, Sequence[PlanAction], or a union "
            f"containing PlanAction; got {ann!r}"
        )
    return actions_meta


def _is_action_type(ann: Any) -> bool:
    """Whether *ann* is `PlanAction` itself or a subclass of it."""
    return isinstance(ann, type) and issubclass(ann, PlanAction)


def _iterate_signature(sig: inspect.Signature) -> cabc.Iterator[tuple[str, Parameter]]:
    """Yield `(name, Parameter)` for each parameter of *sig*, skipping `self`/`cls`."""
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


def _is_plain(ann: Any) -> bool:
    """Return True for a type one input shows: a primitive, an `Enum` or a `Literal`."""
    return (
        ann in _PRIMITIVE_TYPES
        or safe_issubclass(ann, enum.Enum)
        or get_origin(ann) is Literal
    )


def _can_show(ann: Any) -> bool:
    """Return True if a view can be expected to build an input for *ann*.

    Imports no toolkit, so it can run before any application object exists.
    A container, mapping, tuple or union can be shown when every type inside
    it can, a mapping key being a plain type; a device, `Any`, and a container
    no built-in satisfies cannot.
    """
    if isdevice(ann):
        return False
    if _is_plain(ann):
        return True
    members = union_members(ann)
    if members:
        rest = [member for member in members if member is not NoneType]
        return bool(rest) and all(_can_show(member) for member in rest)
    if is_mapping(ann):
        key, value = get_args(ann)
        return _is_plain(key) and _can_show(value)
    if is_fixed_tuple(ann):
        return all(_can_show(member) for member in get_args(ann))
    if container_type(ann) is not None:
        return _can_show(get_args(ann)[0])
    return False


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
    """Inspect *plan* and return a `PlanSpec` with one `ParamDescription` per parameter.

    Parameters
    ----------
    plan
        The plan function or bound method, a generator function annotated to
        return a `MsgGenerator`.
    devices
        The session's devices, giving `choices` for parameters annotated
        with an `OADevice` subtype.

    Raises
    ------
    TypeError
        If *plan* is not a generator function or its return type is not a
        `MsgGenerator` (`Generator[Msg, Any, Any]`).
    UnresolvableAnnotationError
        If an annotation names something missing at runtime, or no view can
        build a control for it.
    ValueError
        If *plan* declares two actions of one name.
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
    is_generator = ret_origin is not None and safe_issubclass(
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

        pkind = ParamKind(param.kind)

        # Action parameters never get a widget, so they skip dispatch
        if actions_meta is not None:
            fields = _FieldsFromAnnotation()
        else:
            fields = _fields_from_annotation(ann, pkind, devices)

        shown = (
            actions_meta is not None
            or pkind is ParamKind.VAR_KEYWORD
            or fields.choices is not None
            or _can_show(ann)
        )
        # refuse now: failing here is clearer than a broken control or a
        # crash once the plan runs
        if not shown and param.default is _empty:
            raise UnresolvableAnnotationError(func_obj.__name__, name, ann)

        params.append(
            ParamDescription(
                name=name,
                kind=pkind,
                annotation=ann,
                default=param.default,
                choices=fields.choices,
                multiselect=fields.multiselect,
                hidden=not shown,
                actions=actions_meta,
                device_proto=fields.device_proto,
            )
        )

    declared = [
        action.name
        for description in params
        if description.actions is not None
        for action in (
            [description.actions]
            if isinstance(description.actions, PlanAction)
            else description.actions
        )
    ]
    twice = sorted({name for name in declared if declared.count(name) > 1})
    if twice:
        raise ValueError(
            f"plan {func_obj.__name__!r} declares more than one action named "
            f"{', '.join(repr(name) for name in twice)}; a name tells the "
            "actions of a plan apart"
        )

    marked = getattr(func_obj, "__continuous__", None)

    return PlanSpec(
        name=func_obj.__name__,
        docs=inspect.getdoc(func_obj) or "No documentation available.",
        parameters=params,
        continuous=marked is not None,
        pausable=marked is not None and marked.pausable,
    )


def collect_arguments(
    spec: PlanSpec,
    values: cabc.Mapping[str, Any],
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Build the `(args, kwargs)` calling a plan, from its `PlanSpec`.

    Parameters
    ----------
    values
        Resolved values by parameter name.

    Notes
    -----
    * `POSITIONAL_ONLY` and `POSITIONAL_OR_KEYWORD` -> `args`, in
      declaration order.
    * `KEYWORD_ONLY` -> `kwargs`.
    * `VAR_POSITIONAL` (`*args`) -> sequence expanded into `args`.
    * `VAR_KEYWORD` (`**kwargs`) -> mapping merged into `kwargs`.
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
    * **Hidden parameters** get their default, so the parameters after them
      keep their places.
    * **Device parameters**: names become `OADevice` instances from
      `devices`.
    * **Everything else** passes unchanged.

    Parameters
    ----------
    spec
        The plan specification.
    param_values
        Parameter values from the interface.
    """
    values: dict[str, Any] = dict(param_values)

    # a parameter with no widget never gets a value from the UI: an action
    # parameter gets its actions, and a hidden one its default, which keeps
    # the parameters after it in their places
    for p in spec.parameters:
        if p.name in values:
            continue
        if p.actions is not None:
            values[p.name] = p.actions
        elif p.hidden:
            values[p.name] = p.default

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
