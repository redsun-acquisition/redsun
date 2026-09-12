from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, get_type_hints

if TYPE_CHECKING:
    from collections.abc import Callable

    from in_n_out import Store

    from redsun.experimental.session import Key

__all__ = ["constant", "provides", "register_shared", "shared_keys"]

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

    Anything asking for ``MotorReadings`` in its `setup` receives the result
    of calling this method on the built component. The return annotation is
    the key, so it must be distinct across the application.
    """
    setattr(method, PROVIDES, True)
    return method


def shared_keys(cls: type) -> dict[str, Key]:
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


def register_shared(
    store: Store, instance: object, cls: type, name: str, seen: dict[Key, str]
) -> None:
    """Register what *instance* shares on *store*, under the annotated types.

    *seen* accumulates the types already claimed, so a clash names both
    components. The value is read once, here, so what a component shares comes
    from what its constructor made and cannot depend on its own `setup`.

    Raises
    ------
    TypeError
        If two components share one type.
    """
    for method_name, provided in shared_keys(cls).items():
        owner = seen.get(provided)
        if owner is not None:
            raise TypeError(
                f"{name!r} and {owner!r} both share "
                f"{getattr(provided, '__name__', provided)!r}. A shared type "
                "identifies one value; give them distinct types."
            )
        seen[provided] = name
        member = getattr(instance, method_name)
        shared = member() if callable(member) else member
        store.register_provider(constant(shared), type_hint=provided)


def constant(value: Any) -> Callable[[], Any]:
    """Return a callable answering with *value*."""

    def read() -> Any:
        return value

    return read
