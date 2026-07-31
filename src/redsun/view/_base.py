from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redsun.view import ViewPosition


@runtime_checkable
class PView(Protocol):
    """Minimal protocol a view component should implement.

    ``name`` is declared as a **read-only property**: the framework only
    reads it, so implementers may satisfy the protocol with a plain
    instance attribute, a class attribute, or a property.

    Notes
    -----
    Access to the virtual container is optional and should be acquired
    by implementing :class:`~redsun.virtual.IsInjectable`.

    Compliance is enforced at build time via ``isinstance`` - class-level
    checks cannot see attributes assigned in ``__init__``.
    """

    @property
    def name(self) -> str:
        """Identity key of the view."""
        ...

    @property
    @abstractmethod
    def view_position(self) -> ViewPosition:
        """Position of the view component in the main view of the UI."""


class View(ABC):
    """Base view class.

    Deliberately does **not** inherit [`PView`][redsun.view.PView]: the
    protocol's read-only ``name`` property descriptor would shadow the
    instance attribute assigned here. Instances satisfy the protocol
    structurally - which is also how any non-ABC view is expected to comply.

    Parameters
    ----------
    name : str
        Identity key of the view. Passed as positional-only argument.
    kwargs : Any, optional
        Additional keyword arguments for view subclasses.
    """

    name: str

    @abstractmethod
    def __init__(
        self,
        name: str,
        /,
        **kwargs: Any,
    ) -> None:
        self.name = name
        super().__init__(**kwargs)

    @property
    @abstractmethod
    def view_position(self) -> ViewPosition:
        """Position of the view component in the main view of the UI."""
