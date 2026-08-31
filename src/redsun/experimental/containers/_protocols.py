from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redsun.experimental.view._placement import Placement

__all__ = ["AttachableComponent", "NamedComponent"]


@runtime_checkable
class NamedComponent(Protocol):
    """A component that knows the name it was declared under.

    Every component clears this, presenters and views alike. A session may
    declare two components of one class, and the declared name is the only
    thing telling them apart, so one that discards the name it was constructed
    with cannot be identified in anything it emits.

    Declared as a read-only property because the framework only reads it: a
    plain instance attribute, a class attribute or a property all satisfy it.
    """

    @property
    def name(self) -> str:
        """Identity key of the component."""
        ...


@runtime_checkable
class AttachableComponent(NamedComponent, Protocol):
    """A component the frontend can attach, and where it asks to go.

    ``placement`` is the whole of the difference between a view and a
    presenter, and it is what the frontend reads to attach the view.
    Answering it from the class rather than from a value assigned in
    ``__init__`` lets a container refuse a view its frontend cannot attach
    before anything is built.
    """

    @property
    def placement(self) -> Placement:
        """Where the component asks to be attached."""
        ...
