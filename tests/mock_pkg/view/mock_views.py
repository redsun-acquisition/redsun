from __future__ import annotations

from typing import Any

from sunflare.view.qt import QtView
from sunflare.view import ViewPosition


class MockQtView(QtView):
    """Mock Qt view for testing."""

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)

    @property
    def view_position(self) -> ViewPosition:
        return ViewPosition.CENTER
