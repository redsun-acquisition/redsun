import pytest
from qtpy import QtWidgets as QtW

from redsun.view import PView, View, ViewPosition
from redsun.view.qt import QtView
from redsun.virtual import IsInjectable, IsProvider, VirtualContainer


def test_qtview_subclassing() -> None:
    """Test that QtView is a virtual subclass of View."""
    assert issubclass(QtView, View)


def test_base_view(bus: VirtualContainer) -> None:
    """Test basic View functionality — no virtual_container required."""

    class TestView(View):
        def __init__(self, name: str) -> None:
            super().__init__(name)

        @property
        def view_position(self) -> ViewPosition:
            return ViewPosition.CENTER

    view = TestView("my_view")

    assert isinstance(view, View)
    assert isinstance(view, PView)
    assert issubclass(TestView, View)
    assert view.name == "my_view"
    assert view.view_position == ViewPosition.CENTER


@pytest.mark.qt
def test_presenter_is_provider(bus: VirtualContainer) -> None:
    """Test that a presenter can optionally implement IsProvider."""

    class ProviderView(QtView):
        def __init__(
            self,
            name: str,
        ) -> None:
            super().__init__(name)

        def register_providers(self, container: VirtualContainer) -> None:
            pass  # would register DI providers here

    app = QtW.QApplication.instance() or QtW.QApplication([])
    assert app is not None

    view = ProviderView("view")
    assert isinstance(view, IsProvider)
    assert issubclass(ProviderView, IsProvider)


def test_view_is_injectable(bus: VirtualContainer) -> None:
    """Test that a view can optionally implement IsInjectable."""

    class InjectableView(View, IsInjectable):
        def __init__(self, name: str) -> None:
            super().__init__(name)

        @property
        def view_position(self) -> ViewPosition:
            return ViewPosition.LEFT

        def inject_dependencies(self, container: VirtualContainer) -> None:
            pass  # would pull providers from container here

    view = InjectableView("injectable_view")
    assert isinstance(view, IsInjectable)
    assert issubclass(InjectableView, IsInjectable)


@pytest.mark.qt
def test_base_qt_view(bus: VirtualContainer) -> None:
    """Test basic QtView functionality."""

    class TestQtView(QtView):
        def __init__(self, name: str) -> None:
            super().__init__(name)

        @property
        def view_position(self) -> ViewPosition:
            return ViewPosition.CENTER

    app = QtW.QApplication.instance() or QtW.QApplication([])
    assert app is not None

    view = TestQtView("qt_view")

    assert isinstance(view, View)
    assert isinstance(view, PView)
    assert view.name == "qt_view"
    assert view.view_position == ViewPosition.CENTER
