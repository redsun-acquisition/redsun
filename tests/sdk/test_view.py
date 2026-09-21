from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from redsun.view import PView, View, ViewPosition
from redsun.view.qt import QtView
from redsun.virtual import IsInjectable, IsProvider

if TYPE_CHECKING:
    from qtpy.QtWidgets import QApplication

    from redsun.virtual import VirtualContainer


def test_qtview_subclassing() -> None:
    """Test that QtView is a virtual subclass of View."""
    assert issubclass(QtView, View)


def test_base_view(bus: VirtualContainer) -> None:
    """Test basic View functionality - no virtual_container required."""

    class TestView(View):
        def __init__(self, name: str) -> None:
            super().__init__(name)

        @property
        def view_position(self) -> ViewPosition:
            return ViewPosition.CENTER

    view = TestView("my_view")

    assert isinstance(view, PView)


@pytest.mark.qt
def test_presenter_is_provider(qapp: QApplication) -> None:
    """Test that a presenter can optionally implement IsProvider."""

    class ProviderView(QtView):
        def __init__(
            self,
            name: str,
        ) -> None:
            super().__init__(name)

        def register_providers(self, _: VirtualContainer) -> None:
            pass  # would register DI providers here

        @property
        def view_position(self) -> ViewPosition:
            return ViewPosition.CENTER

    view = ProviderView("view")
    assert isinstance(view, IsProvider)
    assert issubclass(ProviderView, IsProvider)


def test_view_is_injectable() -> None:
    """Test that a view can optionally implement IsInjectable."""

    class InjectableView(View, IsInjectable):
        def __init__(self, name: str) -> None:
            super().__init__(name)

        @property
        def view_position(self) -> ViewPosition:
            return ViewPosition.LEFT

        def inject_dependencies(self, _: VirtualContainer) -> None:
            pass  # would pull providers from container here

    view = InjectableView("injectable_view")
    assert isinstance(view, IsInjectable)
    assert issubclass(InjectableView, IsInjectable)


@pytest.mark.qt
def test_base_qt_view(qapp: QApplication) -> None:
    """Test basic QtView functionality."""

    class TestQtView(QtView):
        def __init__(self, name: str) -> None:
            super().__init__(name)

        @property
        def view_position(self) -> ViewPosition:
            return ViewPosition.CENTER

    view = TestQtView("qt_view")

    assert isinstance(view, PView)


def test_property_based_view_satisfies_protocol() -> None:
    """Read-only protocol members accept property-based, non-Qt implementers."""

    class _HeadlessView:
        def __init__(self, name: str, /) -> None:
            self._name = name

        @property
        def name(self) -> str:
            return self._name

        @property
        def view_position(self) -> ViewPosition:
            return ViewPosition.CENTER

    view: PView = _HeadlessView("h")  # static check
    assert isinstance(view, PView)  # runtime check


def test_attribute_based_view_satisfies_protocol() -> None:
    """Plain instance attributes satisfy the read-only protocol members."""

    class _AttrView:
        def __init__(self, name: str, /) -> None:
            self.name = name
            self.view_position = ViewPosition.LEFT

    view: PView = _AttrView("a")  # static check
    assert isinstance(view, PView)
