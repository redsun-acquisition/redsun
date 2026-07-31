"""Shared helpers for container tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Mapping

C = TypeVar("C")


def component(mapping: Mapping[str, object], name: str, kind: type[C], /) -> C:
    """Fetch a component from a container mapping, checking its class.

    For containers built from a configuration file, where the components are
    named in the file rather than declared in code and the mapping is typed by
    the protocol they satisfy.

    Parameters
    ----------
    mapping : Mapping[str, object]
        A container's ``devices``, ``presenters`` or ``views``.
    name : str
        Key the component was registered under.
    kind : type[C]
        Class the component is expected to be.

    Returns
    -------
    C
        The component, narrowed to *kind*.
    """
    found = mapping[name]
    assert isinstance(found, kind), (
        f"{name!r} is a {type(found).__name__}, expected {kind.__name__}"
    )
    return found
