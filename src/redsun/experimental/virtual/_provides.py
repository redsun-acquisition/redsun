from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, get_type_hints

from redsun.experimental.containers._factories import synthesize

if TYPE_CHECKING:
    from collections.abc import Callable

    from dishka import Provider

    from redsun.experimental.containers._declarations import Declaration, Key

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
    provider: Provider, declaration: Declaration, seen: dict[Key, str]
) -> None:
    """Add the shared values of *declaration* to *provider*.

    Each is bound to that component instance. *seen* accumulates the types
    already claimed, so a clash names both components.

    Raises
    ------
    TypeError
        If two components share one type.
    """
    for method_name, provided in shared(declaration.cls).items():
        owner = seen.get(provided)
        if owner is not None:
            raise TypeError(
                f"{declaration.name!r} and {owner!r} both share "
                f"{getattr(provided, '__name__', provided)!r}. A shared type "
                "identifies one value; give them distinct types."
            )
        seen[provided] = declaration.name
        provider.provide(_bound(declaration, method_name, provided))


def _bound(
    declaration: Declaration, method_name: str, provided: Key
) -> Callable[..., Any]:
    # the method name is closed over here rather than carried as a default
    # argument, which would leak into the signature dishka inspects
    def build(**deps: Any) -> Any:
        member = getattr(deps["component"], method_name)
        return member() if callable(member) else member

    return synthesize(
        build,
        {"component": declaration.key},
        provided,
        f"{declaration.name}_{method_name}",
    )
