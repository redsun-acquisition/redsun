"""Tests for the hook points an experimental session calls."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, cast

import pytest
from qtpy.QtWidgets import QApplication, QMainWindow, QWidget

from redsun.experimental import (
    AppContainer,
    AsHook,
    AsPresenter,
    AsView,
    Declare,
    HookError,
    Serves,
)
from redsun.experimental.containers.container import BUILD_STEPS
from redsun.experimental.containers.qt import Dock, QtAppContainer, QtHook

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

pytestmark = pytest.mark.qt


class Styler:
    """Serves ``configure_application``, recording what it was handed."""

    def __init__(self, style: str = "plain") -> None:
        self.style = style
        self.seen: list[Any] = []

    def configure_application(self, app: QApplication) -> None:
        """Record *app* rather than styling it."""
        self.seen.append(app)


class Brander:
    """Serves ``configure_main_view`` by retitling the window."""

    def configure_main_view(self, view: QMainWindow) -> None:
        """Retitle *view*, so the call is visible from outside."""
        view.setWindowTitle("branded")


class Both(Styler, Brander):
    """One provider for two points, to show that one object serves both."""


class Splash:
    """Serves ``during_build``, recording the span and every step inside it."""

    entered = 0
    exited = 0
    steps: ClassVar[list[str]] = []

    @contextmanager
    def during_build(self, app: QApplication) -> Iterator[Callable[[str], None]]:
        """Open for the whole build, collecting the name of each step."""
        type(self).entered += 1
        try:
            yield type(self).steps.append
        finally:
            type(self).exited += 1


class Founder:
    """Serves ``create_application`` by handing back the running one."""

    seen: ClassVar[list[list[str]]] = []

    def create_application(self, argv: list[str]) -> QApplication:
        """Record *argv* and return the application the test session owns."""
        type(self).seen.append(argv)
        return cast("QApplication", QApplication.instance())


class NotAHook:
    """Declares none of the methods any point calls."""


class Counter:
    """The presenter a build needs for the presenters step to happen."""

    def __init__(self, name: str, /) -> None:
        self.name = name


class Panel(QWidget):
    """The view a build needs for the views step to happen."""

    placement = Dock("left")

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name


class Unanswerable:
    """Presenter asking for something no session declares.

    A component whose constructor raises is logged and skipped, so ending a
    build part way through takes a fault the session cannot go on without.
    """

    def __init__(self, name: str, /, missing: QMainWindow) -> None:
        self.name = name


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    """Clear the class-level records the providers keep between tests."""
    Splash.entered = 0
    Splash.exited = 0
    Splash.steps = []
    Founder.seen = []
    yield


def test_a_container_that_calls_no_point_refuses_a_hook() -> None:
    """Every point belongs to a toolkit, so a plain session has none to offer."""

    class Headless(AppContainer):
        configure_application: AsHook[Styler]

    with pytest.raises(HookError, match="it calls none"):
        Headless().build()


def test_a_hook_runs_at_the_point_its_attribute_names(qapp: Any) -> None:
    """The attribute name is the point, with no marker needed to say so."""

    class App(QtAppContainer):
        configure_application: AsHook[Styler]

    app = App().build()
    try:
        installed = cast("Styler", app.hooks[QtHook.CONFIGURE_APPLICATION])
        assert installed.seen == [qapp]
    finally:
        app.shutdown()


def test_declare_carries_the_providers_arguments(qapp: Any) -> None:
    """A hook is constructed the way everything else declared here is."""

    class App(QtAppContainer):
        configure_application: Annotated[AsHook[Styler], Declare(style="dark")]

    app = App().build()
    try:
        installed = cast("Styler", app.hooks[QtHook.CONFIGURE_APPLICATION])
        assert installed.style == "dark"
    finally:
        app.shutdown()


def test_one_annotation_serves_several_points(qapp: Any) -> None:
    """The class is named once, so one instance answers at both points."""

    class App(QtAppContainer):
        pair: Annotated[
            AsHook[Both],
            Serves(QtHook.CONFIGURE_APPLICATION, QtHook.CONFIGURE_MAIN_VIEW),
        ]

    app = App().build()
    try:
        hooks = app.hooks
        assert hooks[QtHook.CONFIGURE_APPLICATION] is hooks[QtHook.CONFIGURE_MAIN_VIEW]
        assert app.main_window.windowTitle() == "branded"
    finally:
        app.shutdown()


def test_two_declarations_may_not_claim_one_point(qapp: Any) -> None:
    """A point holds one provider, and nothing combines two."""

    class App(QtAppContainer):
        first: Annotated[AsHook[Styler], Serves(QtHook.CONFIGURE_APPLICATION)]
        second: Annotated[AsHook[Both], Serves(QtHook.CONFIGURE_APPLICATION)]

    with pytest.raises(HookError, match="both claim the hook point"):
        App().build()


def test_a_point_the_container_does_not_call_is_refused(qapp: Any) -> None:
    """A misspelled point is named against the four this container calls."""

    class App(QtAppContainer):
        configure_applications: AsHook[Styler]

    with pytest.raises(HookError, match="expected one of: create_application"):
        App().build()


def test_a_provider_missing_the_method_is_refused(qapp: Any) -> None:
    """The point names a protocol, and the provider is checked against it."""

    class App(QtAppContainer):
        configure_application: AsHook[NotAHook]

    with pytest.raises(HookError, match="does not implement ConfiguresApplication"):
        App().build()


def test_the_configuration_names_a_provider(qapp: Any) -> None:
    """A session installs a bundle's hook without naming it in Python."""

    class App(QtAppContainer):
        config: ClassVar[dict[str, Any]] = {
            "hooks": {
                "configure_main_view": {
                    "provider": "mock_bundle.hooks:MockBranding",
                    "kwargs": {"title": "from-file"},
                }
            }
        }

    app = App().build()
    try:
        assert app.main_window.windowTitle() == "from-file"
    finally:
        app.shutdown()


def test_one_point_may_not_be_named_twice_over(qapp: Any) -> None:
    """The class and the configuration are separate, so neither layers."""

    class App(QtAppContainer):
        configure_main_view: AsHook[Brander]
        config: ClassVar[dict[str, Any]] = {
            "hooks": {
                "configure_main_view": {"provider": "mock_bundle.hooks:MockBranding"}
            }
        }

    with pytest.raises(HookError, match="named both on App and in the configuration"):
        App().build()


def test_during_build_brackets_the_build_and_names_every_step(qapp: Any) -> None:
    """A splash opens before the first component and closes once the window is up."""

    class App(QtAppContainer):
        during_build: AsHook[Splash]
        ctrl: AsPresenter[Counter]
        panel: AsView[Panel]

    app = App().build()
    try:
        assert Splash.entered == 1
        assert Splash.exited == 1
        assert Splash.steps == list(BUILD_STEPS)
    finally:
        app.shutdown()


def test_the_span_closes_on_a_failed_build(qapp: Any) -> None:
    """Nothing is left covering an application that never got a window."""

    class App(QtAppContainer):
        during_build: AsHook[Splash]
        broken: AsPresenter[Unanswerable]

    with pytest.raises(TypeError, match="which nothing in the session provides"):
        App().build()
    assert Splash.entered == 1
    assert Splash.exited == 1


def test_create_application_is_consulted_only_with_none_running(
    qapp: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A running application is adopted as it is, whoever else offered one."""

    class App(QtAppContainer):
        create_application: AsHook[Founder]

    App().build().shutdown()
    assert Founder.seen == []

    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: None))
    app = App().build()
    try:
        assert Founder.seen == [sys.argv]
    finally:
        app.shutdown()
