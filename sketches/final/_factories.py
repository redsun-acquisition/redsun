# ruff: noqa
"""Turning declarations into callables dishka can inspect."""

from __future__ import annotations

import inspect
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Any,
    Optional,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from dishka import Has
from typing_extensions import TypeForm

from ._scopes import AppScope, latest

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from dishka import Provider

    from ._declarations import Declaration


def injectable(cls: type, cfg_kwargs: Mapping[str, Any]) -> dict[str, TypeForm[Any]]:
    """Constructor parameters the graph is responsible for.

    Excludes ``name`` (bound by the framework), anything the config supplied,
    and variadics. ``include_extras`` is load-bearing: dishka's own markers
    live in the same ``Annotated`` slot and must survive the copy.
    """
    hints = get_type_hints(cls.__init__, include_extras=True)
    wanted: dict[str, TypeForm[Any]] = {}
    for pname, param in inspect.signature(cls).parameters.items():
        if pname in ("self", "name") or pname in cfg_kwargs:
            continue
        if param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
            continue
        if pname not in hints:
            raise TypeError(
                f"{cls.__name__}.{pname} has no annotation; the container "
                "cannot tell what to inject"
            )
        wanted[pname] = hints[pname]
    return wanted


def optional_arg(hint: TypeForm[Any]) -> TypeForm[Any] | None:
    """``X`` for ``X | None``, keeping any ``Annotated`` metadata on ``X``."""
    if get_origin(hint) not in (Union, UnionType):
        return None
    args = [arg for arg in get_args(hint) if arg is not type(None)]
    return args[0] if len(args) == 1 else None


def synthesize(
    fn: Callable[..., Any],
    params: Mapping[str, TypeForm[Any]],
    returns: TypeForm[Any],
    name: str,
) -> Callable[..., Any]:
    """Give *fn* the public signature ``(**params) -> returns``.

    dishka resolves by reading annotations, so a factory generated at runtime
    needs annotations generated at runtime. Setting ``__annotations__`` alone
    is not enough: ``make_factory`` reads ``signature(source).parameters`` as
    well, and splits dependencies by parameter kind, so a closure taking
    ``**kwargs`` would present no dependencies at all. ``__signature__`` is set
    with it so both views agree and the closure's own parameters stay hidden.
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


def factory(decl: Declaration) -> Callable[..., Any]:
    """The callable dishka inspects and calls.

    Optional parameters stay in the signature: ``register_optionals`` makes
    ``X | None`` resolvable whether or not anything provides ``X``, so this
    needs no knowledge of what the rest of the graph offers.
    """
    params = injectable(decl.cls, decl.cfg_kwargs)

    def build(**deps: Any) -> Any:
        return decl.cls(decl.name, **decl.cfg_kwargs, **deps)

    return synthesize(build, params, decl.key, f"build_{decl.name}")


def register_optionals(
    provider: Provider, decls: list[Declaration], scope: AppScope
) -> None:
    """Make every ``X | None`` any component asks for resolvable.

    One pair per optional type: an alias to ``X`` when the graph has it, and a
    factory returning ``None`` when it does not. `Has` is dishka's own answer
    to "is this available", so nothing here reads a Provider's internals.

    Per type rather than per component, which keeps this linear: registering
    variants of a component instead would be exponential in its number of
    optional parameters.
    """
    seen: set[TypeForm[Any]] = set()
    for decl in decls:
        for hint in injectable(decl.cls, decl.cfg_kwargs).values():
            inner = optional_arg(hint)
            if inner is None or inner in seen:
                continue
            seen.add(inner)
            provider.alias(source=inner, provides=Optional[inner], when=Has(inner))
            provider.provide(
                synthesize(
                    lambda **_: None, {}, Optional[inner], f"absent_{_name(inner)}"
                ),
                scope=scope,
                when=~Has(inner),
            )


def scope_of(decl: Declaration, scopes: Mapping[TypeForm[Any], AppScope]) -> AppScope:
    """A component is built as late as its latest dependency requires.

    Inferred, never declared: asking for a WIRED-scoped dependency is what
    postpones a component, and components that depend on it follow.
    """
    stages = [AppScope.COMPONENT]
    for hint in injectable(decl.cls, decl.cfg_kwargs).values():
        stage = scopes.get(optional_arg(hint) or hint)
        if stage is not None:
            stages.append(stage)
    return latest(*stages)


def resolve_scopes(
    decls: list[Declaration], provided: dict[TypeForm[Any], AppScope]
) -> None:
    """Assign every declaration its stage, and every shared type its owner's.

    A component's stage depends on its dependencies' stages, and a `@provides`
    type's stage is its owner's, so the two are mutually recursive. Iterating
    to a fixpoint settles it: there are three stages, so a component can only
    move twice, and the loop is bounded by that rather than by the graph.

    A dependency the graph never resolves is left alone here and reported by
    dishka, which can say what was missing.
    """
    from ._provides import shared

    owners = {
        provided_type: decl
        for decl in decls
        for provided_type in shared(decl.cls).values()
    }

    for _ in range(len(AppScope) + 1):
        moved = False
        for decl in decls:
            stage = scope_of(decl, provided)
            if stage is not decl.scope:
                decl.scope = stage
                moved = True
        for provided_type, decl in owners.items():
            if provided.get(provided_type) is not decl.scope:
                provided[provided_type] = decl.scope
                moved = True
        if not moved:
            return

    raise TypeError(
        "component stages did not settle; a shared value is very likely "
        "depending, through its owner, on something that depends on it"
    )


def _name(hint: TypeForm[Any]) -> str:
    return getattr(hint, "__name__", str(hint)).replace(".", "_")


__all__ = [
    "factory",
    "injectable",
    "optional_arg",
    "register_optionals",
    "resolve_scopes",
    "scope_of",
    "synthesize",
]
