"""The `remote` marker."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, TypeVar

from ._wiring import marker_of

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["REMOTE_ATTR", "is_remote", "remote"]

F = TypeVar("F", bound="Callable[..., Any]")

REMOTE_ATTR = "__redsun_remote__"


def remote(fn: F, /) -> F:
    """Mark a method as reachable from outside the process.

    Written directly on the `def`, below `@slot` or `@property`.

    Raises
    ------
    TypeError
        If the target is not a plain function, or already carries `@slot`.
    """
    if not inspect.isfunction(fn) or marker_of(fn) is not None:
        raise TypeError(
            f"cannot mark {fn!r} as remote: @remote goes directly on the def, "
            "below @slot or @property"
        )
    setattr(fn, REMOTE_ATTR, True)
    return fn


def is_remote(fn: object) -> bool:
    """Return whether *fn* carries `remote`."""
    return getattr(fn, REMOTE_ATTR, False) is True
