"""Hook providers a bundle ships for a session to name in its configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qtpy.QtWidgets import QApplication


class MockStyle:
    """Records the application it was handed, and the style it was built with."""

    def __init__(self, style: str = "plain") -> None:
        self.style = style
        self.seen: list[Any] = []

    def configure_application(self, app: QApplication) -> None:
        """Take *app* and record it rather than styling anything."""
        self.seen.append(app)


class MockBranding:
    """Renames the window it is shown, so the effect is visible from outside."""

    def __init__(self, title: str = "branded") -> None:
        self.title = title

    def configure_main_view(self, view: Any) -> None:
        """Retitle *view*."""
        view.setWindowTitle(self.title)
