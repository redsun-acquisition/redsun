from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sunflare.view.qt import QtView

if TYPE_CHECKING:
    from sunflare.virtual import VirtualBus


class MockQtView(QtView):
    """Mock Qt view for testing."""

    def __init__(self, virtual_bus: VirtualBus, /, **kwargs: Any) -> None:
        super().__init__(virtual_bus, **kwargs)
