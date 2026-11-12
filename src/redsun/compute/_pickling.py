"""Checks on what crosses to a worker process, and the inline round trip that applies them."""

from __future__ import annotations

import inspect
import pickle
from functools import partial
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

R = TypeVar("R")

PROTOCOL = 5


def underlying(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Return the function a chain of `functools.partial` wraps."""
    while isinstance(fn, partial):
        fn = fn.func
    return fn


def name_of(fn: Callable[..., Any]) -> str:
    """Return the qualified name of *fn*, looking through `functools.partial`."""
    fn = underlying(fn)
    return getattr(fn, "__qualname__", repr(fn))


def check_function(fn: Callable[..., Any]) -> None:
    """Raise `TypeError` if *fn* is a lambda, a closure, a bound method or defined in `__main__`.

    A worker process imports a function by name, so only one defined at module
    level of a module it can import can reach it.
    """
    target = underlying(fn)
    name = name_of(fn)
    if inspect.ismethod(target) or "<lambda>" in name or "<locals>" in name:
        raise TypeError(
            f"{name} cannot be sent to a worker process: "
            "send a function defined at module level"
        )
    if getattr(target, "__module__", None) == "__main__":
        raise TypeError(
            f"{name} is defined in the script being run, which a worker cannot "
            "import: send a function from a module a worker can import"
        )


def argument_labels(
    fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> list[tuple[str, Any]]:
    """Return each argument of a call with the name it is shown under."""
    try:
        return list(inspect.signature(fn).bind(*args, **kwargs).arguments.items())
    except (TypeError, ValueError):
        return [(f"#{index}", value) for index, value in enumerate(args)] + list(
            kwargs.items()
        )


def dumps_call(
    fn: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    buffer_callback: Callable[[pickle.PickleBuffer], object] | None = None,
) -> bytes:
    """Pickle a call, and name the function or argument that cannot be pickled.

    Raises
    ------
    TypeError
        If the call cannot be pickled; the message names the culprit.
    """
    try:
        return pickle.dumps(
            (fn, args, kwargs), protocol=PROTOCOL, buffer_callback=buffer_callback
        )
    except Exception as error:
        name = name_of(fn)
        for label, value in [("fn", fn), *argument_labels(fn, args, kwargs)]:
            try:
                pickle.dumps(value, protocol=PROTOCOL)
            except Exception:  # noqa: BLE001 - the first that fails is the culprit
                raise TypeError(f"{name}({label}=...): {error}") from error
        raise TypeError(f"{name}(): {error}") from error


def round_trip(
    fn: Callable[..., R], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> R:
    """Run a call as a worker process would: pickled in, and its result pickled out."""
    fn, args, kwargs = pickle.loads(dumps_call(fn, args, kwargs))
    result = fn(*args, **kwargs)
    try:
        sent: bytes = pickle.dumps(result, protocol=PROTOCOL)
    except Exception as error:
        raise TypeError(
            f"{name_of(fn)}() returned a value that cannot be pickled: {error}"
        ) from error
    return pickle.loads(sent)  # type: ignore[no-any-return]
