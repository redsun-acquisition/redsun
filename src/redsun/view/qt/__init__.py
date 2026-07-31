from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from qtpy.QtWidgets import QWidget

from redsun.view import View

if TYPE_CHECKING:
    from typing import Any

    from redsun.view import ViewPosition


class QtView(QWidget):
    """Abstract base Qt widget implementing the View protocol.

    Every slot on a Qt view is delivered on the main thread unless the slot or
    the connection says otherwise, since touching a widget from any other
    thread is undefined.

    Parameters
    ----------
    name : str
        Identity key of the view. Passed as positional-only argument.
    kwargs : Any, optional
        Additional keyword arguments for view subclasses.

    !!! note
        ``kwargs`` are kept for consistency but not forwarded to
        ``QWidget.__init__``.
    """

    __redsun_slot_thread__ = "main"

    @abstractmethod
    def __init__(
        self,
        name: str,
        /,
        **kwargs: Any,
    ) -> None:
        self.name = name
        super().__init__()

    @property
    @abstractmethod
    def view_position(self) -> ViewPosition:
        """Position of the view component in the main view of the UI."""


View.register(QtView)  # type: ignore[type-abstract]

__all__ = ["QtView"]
