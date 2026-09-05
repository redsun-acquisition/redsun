from __future__ import annotations

import inspect
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Any,
    Union,
    get_args,
    get_origin,
)

from typing_extensions import TypeForm

from redsun.experimental.session._declarations import takes_name_by_keyword
from redsun.experimental.virtual._requires import Maybe, key_for, question_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from redsun.experimental.session._declarations import Declaration, Key
    from redsun.experimental.virtual._requires import Question

__all__ = [
    "constructor",
    "defaulted",
    "factory",
    "injectable",
    "optional_arg",
    "provider",
    "requirements",
    "synthesize",
]


def synthesize(
    fn: Callable[..., Any],
    params: Mapping[str, Key],
    returns: Key,
    name: str,
) -> Callable[..., Any]:
    """Give *fn* the public signature ``(**params) -> returns``.

    Both ``__annotations__`` and ``__signature__`` are set: the graph reads the
    signature to learn each parameter's kind and the annotations to learn its
    type, so a closure taking ``**kwargs`` would otherwise present no
    dependencies at all.

    Every name appearing in *params* or *returns* must resolve at runtime; the
    graph evaluates them, and an import made only for type checking fails there.
    """
    fn.__name__ = name
    fn.__qualname__ = name
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
    try:
        return inspect.signature(cls, eval_str=True)
    except NameError as e:
        raise TypeError(
            f"cannot read the constructor of {cls.__qualname__}: {e.name!r} is "
            "not available at runtime. A type a component is injected by must "
            "be imported outside 'if TYPE_CHECKING', because the graph "
            "evaluates the annotation."
        ) from e


def injectable(
    cls: type, cfg_kwargs: Mapping[str, Any], binds_name: bool = True
) -> dict[str, TypeForm[Any]]:
    """Return the constructor parameters the session is responsible for.

    Excludes anything the configuration supplied and variadics, and ``name``
    when the session binds it. A shared service is given no name, so every
    parameter of one is the session's to answer.

    A parameter carrying a default is widened to ``X | None``, so the session
    fills it when something provides ``X`` and leaves the default alone when
    nothing does. A question at most one component may answer is widened the
    same way, since nothing may answer it.

    Annotations are read from the signature rather than from ``__init__``,
    because a class may synthesize one: a pydantic model's real ``__init__``
    takes ``**data``, and its fields appear only in the signature.

    Raises
    ------
    TypeError
        If a remaining parameter carries no annotation.
    """
    wanted: dict[str, TypeForm[Any]] = {}
    bound = ("self", "name") if binds_name else ("self",)
    for pname, param in constructor(cls).parameters.items():
        if pname in bound or pname in cfg_kwargs:
            continue
        if param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
            continue
        if param.annotation is param.empty:
            raise TypeError(
                f"{cls.__name__}.{pname} has no annotation; the session "
                "cannot tell what to inject"
            )
        hint = param.annotation
        question = question_of(hint)
        if question is not None:
            key = key_for(question)
            wanted[pname] = key | None if isinstance(question.marker, Maybe) else key
            continue
        if param.default is not param.empty and not _is_union(hint):
            hint = hint | None
        wanted[pname] = hint
    return wanted


def requirements(declarations: list[Declaration]) -> dict[Question, list[str]]:
    """Return each question the declarations ask, and who asks it.

    One entry per question, not per component: the answer is the same for every
    component that asks, and the names are what an unanswerable question is
    reported against.
    """
    found: dict[Question, list[str]] = {}
    for declaration in declarations:
        for pname, param in constructor(declaration.cls).parameters.items():
            if pname in declaration.cfg_kwargs:
                continue
            question = question_of(param.annotation)
            if question is None:
                continue
            askers = found.setdefault(question, [])
            if declaration.name not in askers:
                askers.append(declaration.name)
    return found


def defaulted(cls: type, names: Iterable[str]) -> set[str]:
    """Return those of *names* the constructor of *cls* gives a default."""
    params = inspect.signature(cls).parameters
    return {
        name
        for name in names
        if name in params and params[name].default is not inspect.Parameter.empty
    }


def optional_arg(hint: TypeForm[Any]) -> TypeForm[Any] | None:
    """Return ``X`` for ``X | None``, or ``None`` for anything else."""
    if not _is_union(hint):
        return None
    args = [arg for arg in get_args(hint) if arg is not type(None)]
    return args[0] if len(args) == 1 else None


def _is_union(hint: TypeForm[Any]) -> bool:
    return get_origin(hint) in (Union, UnionType)


def factory(
    declaration: Declaration, on_built: Callable[[Declaration, Any], None]
) -> Callable[..., Any]:
    """Return the callable the store fills and calls for *declaration*.

    *on_built* runs the moment the instance exists, which is what makes the
    order components are created in observable: the graph, not the caller,
    decides it.

    Optional parameters stay in the signature: the store fills ``X | None``
    with ``None`` when nothing provides ``X``. A parameter answered that way is
    left out of the call, so its own default applies.
    """
    params = injectable(declaration.cls, declaration.cfg_kwargs)
    optional = defaulted(declaration.cls, params)
    # a pydantic model exposes its fields as keyword-only, so the name cannot
    # travel positionally to every component
    by_keyword = takes_name_by_keyword(declaration.cls)

    def build(**deps: Any) -> Any:
        supplied = {
            pname: value
            for pname, value in deps.items()
            if value is not None or pname not in optional
        }
        named = {"name": declaration.name} if by_keyword else {}
        positional = () if by_keyword else (declaration.name,)
        instance = declaration.cls(
            *positional, **named, **declaration.cfg_kwargs, **supplied
        )
        on_built(declaration, instance)
        return instance

    return synthesize(build, params, declaration.key, f"build_{declaration.name}")


def provider(cls: type, name: str) -> Callable[..., Any]:
    """Return the callable the store fills to build the shared service *cls*.

    A provider takes no name of its own, so every annotated parameter of its
    constructor is the store's to answer, ``name`` included.
    """
    params = injectable(cls, {}, binds_name=False)

    def build(**deps: Any) -> Any:
        return cls(**deps)

    return synthesize(build, params, cls, f"build_{name}")
