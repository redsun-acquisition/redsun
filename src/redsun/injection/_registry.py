"""The table of what a session provides, built over `diwire`."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from typing import (
    Annotated,
    Final,
    TypeAlias,
    TypeVar,
    get_args,
    get_origin,
)

from diwire import (
    Component,
    Container,
    DependencyRegistrationPolicy,
    Lifetime,
    MissingPolicy,
    ResolverContext,
)

from .._structural import is_optional, optional_arg
from ..errors import RegistrationError

R = TypeVar("R")

SESSION: Final = "<session>"
"""Owner recorded for what the session itself provides."""

Ask: TypeAlias = Callable[[object], tuple[object] | None]
"""Answers a key nobody registered with a one-tuple holding its value, or `None`."""


def key_of(key: object) -> object:
    """Return *key* without the `Annotated` metadata `diwire` ignores."""
    if get_origin(key) is not Annotated:
        return key
    base, *metadata = get_args(key)
    kept = tuple(item for item in metadata if isinstance(item, Component))
    return Annotated[(base, *kept)] if kept else base


class Registry:
    """What one session provides, one key to one value.

    A registry belongs to one session. A key holds one value, and every lookup
    matches its key exactly: a subclass is not answered by a value registered
    under its base class, and a union is not answered by a value registered
    under one of its members, apart from `X | None`, which `X` answers. `ask`
    answers a key nobody registered, each time a provider for it is called.
    """

    __slots__ = ("_ask", "_container", "_owners")

    def __init__(self, ask: Ask | None = None) -> None:
        self._ask = ask
        self._container = Container(
            missing_policy=MissingPolicy.ERROR,
            dependency_registration_policy=DependencyRegistrationPolicy.IGNORE,
            # diwire's shared default context keeps the latest container alive
            # for good, and with it everything its factories refer to
            resolver_context=ResolverContext(),
            use_resolver_context=False,
        )
        self._owners: dict[object, str] = {}

    def register(
        self, key: object, factory: Callable[[], object], *, owner: str
    ) -> None:
        """Register *factory* under *key*, called on every request.

        Raises
        ------
        RegistrationError
            If *key* is registered already, metadata `diwire` ignores aside.
        """
        held = key_of(key)
        if held in self._owners:
            raise RegistrationError(
                f"'{getattr(held, '__name__', held)}' is provided by "
                f"'{self._owners[held]}' already, so '{owner}' cannot provide it too"
            )
        self._container.add_factory(factory, provides=key, lifetime=Lifetime.TRANSIENT)
        self._owners[held] = owner

    def _registered(self, key: object) -> object | None:
        if key_of(key) in self._owners:
            return key
        inner = optional_arg(key)
        if inner is not None and key_of(inner) in self._owners:
            return inner
        return None

    def providers(self, key: object) -> Iterator[Callable[[], object]]:
        """Yield a provider of *key*, or none when nothing answers it."""
        found = self._registered(key)
        if found is not None:
            yield lambda: self._container.resolve(found)
        elif self._ask is not None and self._ask(key) is not None:
            ask = self._ask

            def asked() -> object | None:
                answer = ask(key)
                return None if answer is None else answer[0]

            yield asked

    def call(self, fn: Callable[..., R], /, **passed: object) -> R:
        """Call *fn*, filling each parameter not in *passed* from the keys held.

        A parameter with a default keeps it when nothing answers. One written
        `X | None`, or a union with `None` among its members, receives `None`
        then. A `None` from a held key does not answer a required parameter.

        Raises
        ------
        TypeError
            If a required parameter has no value, naming each.
        """
        filled: dict[str, object] = {}
        missing: list[str] = []
        for name, param in inspect.signature(fn, eval_str=True).parameters.items():
            if name in passed or param.kind in (
                param.VAR_POSITIONAL,
                param.VAR_KEYWORD,
            ):
                continue
            hint = param.annotation
            found = self._registered(hint)
            value = None if found is None else self._container.resolve(found)
            if value is not None:
                filled[name] = value
            elif param.default is not param.empty:
                continue
            elif is_optional(hint):
                filled[name] = None
            else:
                missing.append(f"'{name}'")
        if missing:
            raise TypeError(
                f"cannot fill {', '.join(missing)} of {getattr(fn, '__name__', fn)}"
            )
        return fn(**passed, **filled)
