from __future__ import annotations

import dataclasses
import inspect
import sys
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin, is_typeddict

from pydantic import BaseModel, TypeAdapter
from pydantic.errors import PydanticInvalidForJsonSchema, PydanticSchemaGenerationError

from .._structural import is_optional, without_none
from ..compute._pool import PoolExecutor
from ..injection._census import devices_protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from typing_extensions import TypeForm

    from ._declarations import Declaration, Key
    from ._protocols import HasSetup

__all__ = [
    "constructor",
    "defaulted",
    "factory",
    "get_setup_params",
    "injectable",
    "provider",
    "resolved",
    "setup_call",
    "synthesize",
]


def synthesize(
    fn: Callable[..., Any],
    params: Mapping[str, Key],
    returns: Key,
    name: str,
) -> Callable[..., Any]:
    """Give *fn* the public signature `(**params) -> returns`.

    Both `__annotations__` and `__signature__` are set.

    Every name appearing in *params* or *returns* must resolve at runtime; the
    graph evaluates them, and an import made only for type checking fails there.
    """
    fn.__name__ = name
    fn.__qualname__ = name
    # the graph reads each parameter's kind from the signature and its type
    # from the annotations; a closure taking **kwargs shows neither
    fn.__annotations__ = {**params, "return": returns}
    fn.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        parameters=[
            inspect.Parameter(
                pname, inspect.Parameter.KEYWORD_ONLY, annotation=annotation
            )
            for pname, annotation in params.items()
        ],
        return_annotation=returns,
    )
    return fn


def constructor(cls: type) -> inspect.Signature:
    """Return the signature of *cls*, with its annotations resolved.

    Raises
    ------
    TypeError
        If an annotation names something that does not exist at runtime.
    """
    return resolved(cls, f"the constructor of {cls.__qualname__}")


def resolved(target: Any, label: str) -> inspect.Signature:
    """Return the signature of *target*, with its annotations resolved.

    The generated constructor of a dataclass carries the fields of its
    bases, so each field is resolved in the module of the class declaring it,
    not in the module of *target*.

    Raises
    ------
    TypeError
        If an annotation names something that does not exist at runtime.
    """
    try:
        if dataclasses.is_dataclass(target) and isinstance(target, type):
            signature = inspect.signature(target)
            return signature.replace(
                parameters=[
                    param.replace(annotation=field_type(target, param))
                    for param in signature.parameters.values()
                ]
            )
        return inspect.signature(target, eval_str=True)
    except NameError as error:
        raise TypeError(
            f"cannot read {label}: {error.name!r} is "
            "not available at runtime. A type a component is injected by must "
            "be imported outside 'if TYPE_CHECKING', because the graph "
            "evaluates the annotation."
        ) from error


def field_type(cls: type, param: inspect.Parameter) -> Any:
    """Return the annotation of *param*, evaluated where its field is declared.

    Raises
    ------
    NameError
        If the annotation names something its module does not define.
    """
    annotation = param.annotation
    if not isinstance(annotation, str):
        return annotation
    for owner in cls.__mro__:
        if param.name in vars(owner).get("__annotations__", {}):
            module = sys.modules[owner.__module__]
            return eval(annotation, vars(module), dict(vars(owner)))
    # a parameter of a constructor written by hand, not of a field
    init = next(
        vars(owner)["__init__"] for owner in cls.__mro__ if "__init__" in vars(owner)
    )
    return eval(annotation, getattr(init, "__globals__", {}))


def injectable(
    cls: type,
    cfg_kwargs: Mapping[str, Any],
    binds_name: bool = True,
    passed: Iterable[str] = (),
) -> dict[str, TypeForm[Any]]:
    """Return the constructor parameters the session is responsible for.

    Excludes anything the configuration supplied, variadics, *passed*, and
    `name` when the session binds it. A shared service is given no name, so
    every parameter of one is the session's to answer.

    A parameter carrying a default is widened to `X | None`, so the session
    fills it when something provides `X` and leaves the default alone when
    nothing does. A parameter asking for devices with `DevicesOf` is left
    out, the session passing the devices itself.

    Annotations are read from the class signature rather than from
    `__init__`.

    Raises
    ------
    TypeError
        If a remaining parameter carries no annotation.
    """
    bound = ("self", "name", *passed) if binds_name else ("self", *passed)
    # a pydantic model's own __init__ takes **data; its fields appear only in
    # the class signature
    return wanted_from(constructor(cls), cls.__name__, cfg_kwargs, bound)


def get_setup_params(cls: type[HasSetup[...]]) -> dict[str, TypeForm[Any]]:
    """Return the parameters of `cls.setup` the session is responsible for.

    Raises
    ------
    TypeError
        If a parameter carries no annotation, or names a type that does not
        exist at runtime.
    """
    signature = resolved(cls.setup, f"{cls.__qualname__}.setup")
    return wanted_from(signature, f"{cls.__name__}.setup", {}, ("self",))


def wanted_from(
    signature: inspect.Signature,
    owner: str,
    cfg_kwargs: Mapping[str, Any],
    bound: tuple[str, ...],
) -> dict[str, TypeForm[Any]]:
    """Return the parameters of *signature* the session is responsible for."""
    wanted: dict[str, TypeForm[Any]] = {}
    for pname, param in signature.parameters.items():
        if pname in bound or pname in cfg_kwargs:
            continue
        if param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
            continue
        if param.annotation is param.empty:
            raise TypeError(
                f"{owner}.{pname} has no annotation; the session "
                "cannot tell what to inject"
            )
        hint = param.annotation
        if devices_protocol(hint) is not None:
            continue
        if param.default is not param.empty and not is_optional(hint):
            hint = hint | None
        wanted[pname] = hint
    return wanted


def device_questions(cls: type, cfg_kwargs: Mapping[str, Any]) -> dict[str, type]:
    """Return the constructor parameters of *cls* asking for devices, by protocol.

    A parameter the configuration fills is left out.
    """
    found: dict[str, type] = {}
    for pname, param in constructor(cls).parameters.items():
        if pname in cfg_kwargs:
            continue
        protocol = devices_protocol(param.annotation)
        if protocol is not None:
            found[pname] = protocol
    return found


def defaulted(cls: type, names: Iterable[str]) -> set[str]:
    """Return those of *names* the constructor of *cls* gives a default."""
    params = inspect.signature(cls).parameters
    return {
        name
        for name in names
        if name in params and params[name].default is not inspect.Parameter.empty
    }


def supplied(deps: Mapping[str, Any], optional: set[str]) -> dict[str, Any]:
    """Return *deps* without the defaulted parameters the registry answered with `None`.

    Each one left out keeps the default its constructor gives it.
    """
    return {
        pname: value
        for pname, value in deps.items()
        if value is not None or pname not in optional
    }


def factory(
    declaration: Declaration,
    on_built: Callable[[Declaration, Any], None],
    passed: Mapping[str, object],
) -> Callable[..., Any]:
    """Return the callable the registry fills and calls for *declaration*.

    *on_built* runs the moment the instance exists, which is what makes the
    order components are created in observable: the graph, not the caller,
    decides it.

    Optional parameters stay in the signature: the registry fills `X | None`
    with `None` when nothing provides `X`. A parameter answered that way is
    left out of the call, so its own default applies. *passed* reaches the
    constructor by keyword, untouched.
    """
    params = injectable(declaration.cls, declaration.cfg_kwargs, passed=passed)
    optional = defaulted(declaration.cls, params)

    def build(**deps: Any) -> Any:
        instance = declaration.cls(
            name=declaration.name,
            **passed,
            **declaration.cfg_kwargs,
            **supplied(deps, optional),
        )
        on_built(declaration, instance)
        return instance

    return synthesize(build, params, declaration.key, f"build_{declaration.name}")


def setup_call(
    instance: HasSetup[...], name: str, answers: Mapping[str, object]
) -> Callable[..., Any]:
    """Return the callable the registry fills and calls to set *instance* up.

    *answers* reach `setup` as they are, and the registry is asked for the other
    parameters only.
    """
    params = {
        pname: hint
        for pname, hint in get_setup_params(type(instance)).items()
        if pname not in answers
    }

    def run(**deps: Any) -> None:
        instance.setup(**answers, **deps)

    return synthesize(run, params, None, f"set_up_{name}")


def provider(cls: type, name: str) -> Callable[..., Any]:
    """Return the callable the registry fills to build the shared service *cls*.

    A provider takes no name of its own, so every annotated parameter of its
    constructor is the registry's to answer, `name` included. A parameter with a
    default that nothing provides keeps its default, as a component's does.
    """
    params = injectable(cls, {}, binds_name=False)
    optional = defaulted(cls, params)

    def build(**deps: Any) -> Any:
        return cls(**supplied(deps, optional))

    return synthesize(build, params, cls, f"build_{name}")


def positional_only(cls: type) -> list[str]:
    """Return the parameters of *cls* only a positional argument can fill.

    One carrying a default is left out, since leaving it unfilled is legal.
    """
    try:
        params = inspect.signature(cls).parameters.values()
    except (TypeError, ValueError):
        return []
    return [
        param.name
        for param in params
        if param.kind is inspect.Parameter.POSITIONAL_ONLY
        and param.default is inspect.Parameter.empty
    ]


@dataclasses.dataclass(frozen=True)
class Filled:
    """A constructor parameter the session fills by its type."""

    name: str
    """The parameter's name."""

    type: str
    """Its type, as text a user can look up."""

    required: bool
    """Whether it has no default, so the build fails when nothing fills it."""

    file: bool
    """Whether a session file may give it instead."""


@dataclasses.dataclass(frozen=True)
class Parameters:
    """A constructor's parameters, sorted by where their values come from."""

    fields: dict[str, tuple[Any, Any]]
    """The keys a session file gives, as `pydantic.create_model` takes them.

    Each is the annotation and the default, `...` when there is none.
    """

    filled: list[Filled]
    """The parameters the session fills by their type."""

    problems: dict[str, str]
    """What is wrong with a parameter, by its name."""

    open: bool
    """Whether the constructor takes `**kwargs`, so any key is accepted."""

    refusal: str | None
    """Why the build cannot construct the class, or `None`."""


def held_name(annotation: object, held: Mapping[object, str]) -> str | None:
    """Return the name *held* gives *annotation*, or `None` when it is not held."""
    return next((name for key, name in held.items() if key == annotation), None)


def type_text(annotation: object, held: Mapping[object, str]) -> str:
    """Return *annotation* as text: its held name, `module:QualName` for a class, else `str()`."""
    name = held_name(annotation, held)
    if name is not None:
        return name
    if isinstance(annotation, type):
        return f"{annotation.__module__}:{annotation.__qualname__}"
    return str(annotation)


def is_model(annotation: object) -> bool:
    """Return whether *annotation* is a `pydantic` model, a dataclass or a `TypedDict`."""
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    if not isinstance(annotation, type):
        return False
    return (
        issubclass(annotation, BaseModel)
        or dataclasses.is_dataclass(annotation)
        or is_typeddict(annotation)
    )


def has_schema(annotation: Any) -> bool:
    """Return whether `pydantic` can write a JSON Schema of *annotation*."""
    try:
        TypeAdapter(annotation).json_schema()
    except (PydanticSchemaGenerationError, PydanticInvalidForJsonSchema):
        return False
    return True


def session_fills(annotation: Any, held: Mapping[object, str]) -> bool:
    """Return whether only the session can give a parameter annotated *annotation*."""
    if devices_protocol(annotation) is not None:
        return True
    hint = without_none(annotation)
    if held_name(hint, held) is not None:
        return True
    if isinstance(hint, type) and issubclass(hint, PoolExecutor):
        return True
    return not has_schema(annotation)


def parameters_of(cls: type, held: Mapping[object, str]) -> Parameters:
    """Sort the constructor parameters of *cls* by where their values come from.

    Each annotation is resolved on its own, so a name missing at runtime is
    reported for its parameter while the others are still sorted. Such a
    name, or a positional-only parameter without a default, makes the class
    one the build cannot construct.

    Parameters
    ----------
    held
        The types the session holds itself, by the name a user looks them up by.

    Raises
    ------
    TypeError
        If the signature of *cls* cannot be read, or a parameter carries a
        malformed `DevicesOf`.
    """
    try:
        signature = inspect.signature(cls)
    except ValueError as error:
        raise TypeError(f"cannot read the signature of {cls.__qualname__}") from error
    fields: dict[str, tuple[Any, Any]] = {}
    filled: list[Filled] = []
    problems: dict[str, str] = {}
    takes_any = False
    refusals: list[str] = []
    blocked = positional_only(cls)
    if blocked:
        refusals.append(
            f"{cls.__qualname__} takes {', '.join(map(repr, blocked))} positionally "
            "only, and the session passes keywords only"
        )
    for pname, param in signature.parameters.items():
        if pname in ("self", "name") or param.kind is param.VAR_POSITIONAL:
            continue
        if param.kind is param.VAR_KEYWORD:
            takes_any = True
            continue
        default = ... if param.default is param.empty else param.default
        if param.kind is param.POSITIONAL_ONLY:
            problems[pname] = "the session passes keywords only"
            continue
        if param.annotation is param.empty:
            problems[pname] = (
                "it has no annotation, so the session cannot tell its type"
            )
            fields[pname] = (Any, default)
            continue
        try:
            annotation = field_type(cls, param)
        except NameError as error:
            problems[pname] = (
                f"its annotation names {error.name!r}, which is not available at runtime"
            )
            refusals.append(
                f"cannot read the constructor of {cls.__qualname__}: {error.name!r} "
                "is not available at runtime"
            )
            continue
        required = default is ...
        if session_fills(annotation, held):
            filled.append(
                Filled(pname, type_text(annotation, held), required, file=False)
            )
            continue
        fields[pname] = (annotation, default)
        if required and is_model(annotation):
            filled.append(Filled(pname, type_text(annotation, held), True, file=True))
    return Parameters(
        fields=fields,
        filled=filled,
        problems=problems,
        open=takes_any,
        refusal="; ".join(refusals) or None,
    )
