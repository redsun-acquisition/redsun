from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, get_type_hints

from .._structural import without_none

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..session._declarations import Key
    from ._registry import Registry

__all__ = [
    "claim_shared",
    "constant",
    "provides",
    "read_shared",
    "register_shared",
    "shared_keys",
]

PROVIDES = "__redsun_provides__"

F = TypeVar("F", bound="Callable[..., Any]")
T = TypeVar("T")


def provides(method: F) -> F:
    """Share a method's return value under the type it is annotated with.

    ```python
    class MotorPresenter:
        @provides
        def readings(self) -> MotorReadings:
            return MotorReadings(...)
    ```

    Anything asking for `MotorReadings` in its `setup` receives the result
    of calling this method on the built component. The return annotation is
    the key, so it must be distinct across the application.
    """
    setattr(method, PROVIDES, True)
    return method


def shared_keys(cls: type) -> dict[str, Key]:
    """Return the `provides`-marked members of *cls*, as name to type.

    A member annotated `X | None` is shared as `X`.

    Raises
    ------
    TypeError
        If a marked member has no return annotation.
    """
    found: dict[str, Key] = {}
    for name in dir(cls):
        member = getattr(cls, name, None)
        target = member.fget if isinstance(member, property) else member
        if target is None or not getattr(target, PROVIDES, False):
            continue
        hints = get_type_hints(target, include_extras=True)
        if "return" not in hints:
            raise TypeError(
                f"{cls.__name__}.{name} is marked with 'provides' but has no "
                "return annotation; the annotation is the key consumers use"
            )
        found[name] = without_none(hints["return"])
    return found


def claim_shared(cls: type, name: str, seen: dict[Key, str]) -> dict[str, Key]:
    """Claim the types *cls* shares for *name*, as member name to type.

    *seen* accumulates the types already claimed, so a clash names both
    components.

    Raises
    ------
    TypeError
        If another component claimed a type *cls* shares.
    """
    keys = shared_keys(cls)
    for provided in keys.values():
        owner = seen.get(provided)
        if owner is not None:
            raise TypeError(
                f"{name!r} and {owner!r} both share "
                f"{getattr(provided, '__name__', provided)!r}. A shared type "
                "identifies one value; give them distinct types."
            )
        seen[provided] = name
    return keys


def read_shared(instance: object, keys: dict[str, Key]) -> list[object]:
    """Return the values *instance* shares under *keys*, calling each member once."""
    values: list[object] = []
    for method_name in keys:
        member = getattr(instance, method_name)
        values.append(member() if callable(member) else member)
    return values


def register_shared(
    registry: Registry, instance: object, cls: type, name: str, seen: dict[Key, str]
) -> list[object]:
    """Register what *instance* shares on *registry*, under the annotated types.

    The value is read once, here, so what a component shares comes
    from what its constructor made and cannot depend on its own `setup`.
    Returns the values shared, in the order they were registered.

    Raises
    ------
    TypeError
        If two components share one type.
    RegistrationError
        If the session or a provider registered earlier provides a type
        *instance* shares.
    """
    keys = claim_shared(cls, name, seen)
    values = read_shared(instance, keys)
    for provided, shared in zip(keys.values(), values, strict=True):
        registry.register(provided, constant(shared), owner=name)
    return values


def constant(value: T) -> Callable[[], T]:
    """Return a callable answering with *value*."""

    def read() -> T:
        return value

    return read
