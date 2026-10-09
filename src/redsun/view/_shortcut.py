"""Keys a component's methods answer to, recorded where they are declared."""

from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, TypeVar, get_args

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["Shortcut", "shortcut"]

Scope = Literal["window", "view"]
"""Where a key acts: anywhere in the window, or while the component's view has focus."""

F = TypeVar("F", bound="Callable[..., object]")

SHORTCUT_ATTR: Final = "__redsun_shortcut__"
"""The attribute `shortcut` records its `Shortcut` under, on the method."""


@dataclass(frozen=True)
class Shortcut:
    """A key that runs a component's method, as `shortcut` recorded it.

    Raises
    ------
    ValueError
        If the key or the title is empty, or the scope is neither `"window"`
        nor `"view"`.
    """

    key: str
    """The key, in app-model's spelling such as `"Ctrl+R"`; `Ctrl` is Command on macOS."""

    title: str
    """What the key does, as the list of shortcuts shows it."""

    scope: Scope = "window"
    """`"window"` for anywhere in the window, `"view"` for while the component's view has focus."""

    mac: str | None = None
    """The key on macOS, when it differs."""

    win: str | None = None
    """The key on Windows, when it differs."""

    linux: str | None = None
    """The key on Linux, when it differs."""

    def __post_init__(self) -> None:
        problems = []
        if not self.key:
            problems.append("its key is empty")
        if not self.title:
            problems.append("its title is empty")
        if self.scope not in get_args(Scope):
            problems.append(f"its scope {self.scope!r} is neither 'window' nor 'view'")
        if problems:
            raise ValueError(f"shortcut: {'; '.join(problems)}")

    def key_here(self) -> str:
        """Return the key on the platform this runs on."""
        here = {"darwin": self.mac, "win32": self.win}.get(sys.platform, self.linux)
        return here or self.key


def shortcut(
    key: str,
    *,
    title: str,
    scope: Scope = "window",
    mac: str | None = None,
    win: str | None = None,
    linux: str | None = None,
) -> Callable[[F], F]:
    """Return a decorator recording that *key* runs the method it decorates.

    The method is returned unchanged, so it can be a slot too. A session
    binds the key once the component is built: anywhere in the window, or
    with `scope="view"` only while the component's own view has focus.

    Raises
    ------
    ValueError
        If the key or the title is empty, or the scope is unknown.
    TypeError
        When applied to a method that needs arguments besides itself, or to a
        coroutine method.
    """
    record = Shortcut(key, title, scope, mac, win, linux)

    def decorate(method: F) -> F:
        if inspect.iscoroutinefunction(method):
            raise TypeError(
                f"{method.__qualname__} is a coroutine method, which a key "
                "cannot run yet; call it from a plain method"
            )
        needed = [
            name
            for name, param in list(inspect.signature(method).parameters.items())[1:]
            if param.default is inspect.Parameter.empty
            and param.kind not in (param.VAR_POSITIONAL, param.VAR_KEYWORD)
        ]
        if needed:
            raise TypeError(
                f"{method.__qualname__} needs {', '.join(map(repr, needed))}, "
                "which a key cannot give it"
            )
        setattr(method, SHORTCUT_ATTR, record)
        return method

    return decorate


def shortcuts(
    component: object,
) -> dict[str, tuple[Callable[[], object], Shortcut]]:
    """Return the decorated methods of *component*, bound, by name, base classes' first.

    The class that defines a method decides: an override without the
    decorator takes the key away.
    """
    found: dict[str, tuple[Callable[[], object], Shortcut]] = {}
    for klass in reversed(type(component).__mro__):
        for name, value in vars(klass).items():
            record = getattr(value, SHORTCUT_ATTR, None)
            if isinstance(record, Shortcut):
                found[name] = (getattr(component, name), record)
            elif name in found:
                del found[name]
    return found
