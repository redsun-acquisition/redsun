# ruff: noqa
"""Letting a component carry its own provider.

`@provides` marks a method whose return value is shared. It is a declaration,
not a hook: it takes no container, knows no build stage, and the author never
names the DI system. The framework reads the marker when it registers the
component and derives a factory bound to that instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, TypeVar, get_type_hints

from typing_extensions import TypeForm

from ._factories import synthesize

if TYPE_CHECKING:
    from dishka import Provider

    from ._declarations import Declaration
    from ._scopes import AppScope

PROVIDES = "__redsun_provides__"

F = TypeVar("F", bound=Callable[..., Any])


def provides(method: F) -> F:
    """Share this method's return value under the type it is annotated with.

    ```python
    class MotorPresenter(Presenter):
        @provides
        def devices_readings(self) -> MotorReadings:
            return MotorReadings(...)
    ```

    Anything asking for `MotorReadings` gets the result of calling this method
    on the built presenter, and is built after it.
    """
    setattr(method, PROVIDES, True)
    return method


def shared(cls: type) -> dict[str, TypeForm[Any]]:
    """The `@provides` methods of *cls*, as ``{method name: provided type}``.

    A method must annotate its return type, and that type must be distinct
    across the application: it is the key consumers resolve.
    """
    found: dict[str, TypeForm[Any]] = {}
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
    provider: Provider,
    decl: Declaration,
    scope: AppScope,
    seen: dict[TypeForm[Any], str],
) -> None:
    """Add *decl*'s shared values to *provider*, bound to that instance.

    Two components sharing one type is refused here rather than at resolution,
    because the message can name both of them.
    """
    for method_name, provided in shared(decl.cls).items():
        owner = seen.get(provided)
        if owner is not None:
            raise TypeError(
                f"{decl.name!r} and {owner!r} both share "
                f"{getattr(provided, '__name__', provided)!r}. A shared type "
                "identifies one value; give them distinct types."
            )
        seen[provided] = decl.name
        provider.provide(_bound(decl, method_name, provided), scope=scope)


def _bound(
    decl: Declaration, method_name: str, provided: TypeForm[Any]
) -> Callable[..., Any]:
    """A factory that reads one shared value off one built component.

    The method name is closed over by this function's scope rather than
    carried as a default argument, so it cannot leak into the signature
    dishka inspects.
    """

    def build(**deps: Any) -> Any:
        member = getattr(deps["component"], method_name)
        return member() if callable(member) else member

    return synthesize(
        build, {"component": decl.key}, provided, f"{decl.name}_{method_name}"
    )


__all__ = ["provides", "register", "shared"]
