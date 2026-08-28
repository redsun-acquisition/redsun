from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redsun.experimental.view._placement import Placement

__all__ = ["PPresenter", "PView"]


@runtime_checkable
class PPresenter(Protocol):
    """What every presenter exposes.

    Members are declared as read-only properties because the framework only
    reads them: a plain instance attribute, a class attribute or a property
    all satisfy them.

    Devices are not part of the shape. A presenter that needs them asks for
    them as a constructor parameter, so one that needs none never holds the
    mapping.
    """

    @property
    def name(self) -> str:
        """Identity key of the presenter."""
        ...


@runtime_checkable
class PView(Protocol):
    """What every view exposes.

    ``placement`` is the whole of the difference between a view and a
    presenter, and it is what the frontend reads to attach the view.
    Answering it from the class rather than from a value assigned in
    ``__init__`` lets a container refuse a view its frontend cannot attach
    before anything is built.
    """

    @property
    def name(self) -> str:
        """Identity key of the view."""
        ...

    @property
    def placement(self) -> Placement:
        """Where the view asks to be attached."""
        ...
