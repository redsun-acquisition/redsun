from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redsun.view import ViewPosition


@runtime_checkable
class PView(Protocol):
    """Protocol of a view component.

    ``name`` is a read-only property, so an instance attribute, a class
    attribute or a property satisfies it.

    Notes
    -----
    A view reaches the virtual container by implementing
    [`IsInjectable`][redsun.virtual.IsInjectable].

    Checked with ``isinstance`` on the built instance, since attributes
    assigned in ``__init__`` do not exist on the class.
    """

    @property
    def name(self) -> str:
        """Identity key of the view."""
        ...

    @property
    @abstractmethod
    def view_position(self) -> ViewPosition:
        """Position of the view in the main window."""


class View(ABC):
    """Base view class.

    Does not inherit [`PView`][redsun.view.PView], whose read-only ``name``
    property would shadow the instance attribute set here. Instances satisfy
    the protocol by shape, like any other view.

    Parameters
    ----------
    name : str
        Identity key of the view, positional-only.
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
        """Position of the view in the main window."""
