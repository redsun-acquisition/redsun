from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, ClassVar

from qtpy.QtWidgets import QWidget

from redsun.view import View

if TYPE_CHECKING:
    from typing import Any

    from redsun.view import ViewPosition
    from redsun.virtual import SlotThread


class QtView(QWidget):
    """Abstract Qt widget implementing the view protocol.

    Slots run on the main thread unless the slot or the connection says
    otherwise, since touching a widget from another thread is undefined.

    Parameters
    ----------
    name : str
        Identity key of the view, positional-only.
    kwargs : Any, optional
        Additional keyword arguments for view subclasses.

    !!! note
        ``kwargs`` are accepted but not passed to ``QWidget.__init__``.
    """

    __redsun_slot_thread__: ClassVar[SlotThread] = "main"

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
        """Position of the view in the main window."""


View.register(QtView)  # type: ignore[type-abstract]

__all__ = ["QtView"]
