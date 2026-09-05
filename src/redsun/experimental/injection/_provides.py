from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, get_type_hints

if TYPE_CHECKING:
    from collections.abc import Callable

    from in_n_out import Store

    from redsun.experimental.session._declarations import Key

__all__ = ["provides", "register", "shared"]

PROVIDES = "__redsun_provides__"

F = TypeVar("F", bound="Callable[..., Any]")


def provides(method: F) -> F:
    """Share a method's return value under the type it is annotated with.

    ```python
    class MotorPresenter:
        @provides
        def readings(self) -> MotorReadings:
            return MotorReadings(...)
    ```

    Anything asking for ``MotorReadings`` receives the result of calling this
    method on the built component, and is built after it. The return
    annotation is the key, so it must be distinct across the application.
    """
    setattr(method, PROVIDES, True)
    return method


def shared(cls: type) -> dict[str, Key]:
    """Return the ``provides``-marked members of *cls*, as name to type.

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
        found[name] = hints["return"]
    return found


def register(
    store: Store, instance: object, cls: type, name: str, seen: dict[Key, str]
) -> None:
    """Register what *instance* shares on *store*, under the annotated types.

    *seen* accumulates the types already claimed, so a clash names both
    components.

    Raises
    ------
    TypeError
        If two components share one type.
    """
    for method_name, provided in shared(cls).items():
        owner = seen.get(provided)
        if owner is not None:
            raise TypeError(
                f"{name!r} and {owner!r} both share "
                f"{getattr(provided, '__name__', provided)!r}. A shared type "
                "identifies one value; give them distinct types."
            )
        seen[provided] = name
        store.register_provider(value(instance, method_name), type_hint=provided)


def value(instance: object, method_name: str) -> Callable[[], Any]:
    """Return a callable giving what *instance* shares through *method_name*."""

    def read() -> Any:
        member = getattr(instance, method_name)
        return member() if callable(member) else member

    return read
