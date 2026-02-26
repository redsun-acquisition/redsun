from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redsun.view import ViewPosition


@runtime_checkable
class PView(Protocol):
    """Minimal protocol a view component should implement.

    Attributes
    ----------
    name : str
        Identity key of the view.

    Notes
    -----
    Access to the virtual container is optional and should be acquired
    by implementing :class:`~redsun.virtual.IsInjectable`.
    """

    name: str

    @property
    @abstractmethod
    def view_position(self) -> ViewPosition:
        """Position of the view component in the main view of the UI."""


class View(PView, ABC):
    """Base view class.

    Parameters
    ----------
    name : str
        Identity key of the view. Passed as positional-only argument.
    kwargs : Any, optional
        Additional keyword arguments for view subclasses.
    """

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
