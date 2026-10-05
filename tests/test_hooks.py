"""Tests for the hook points a session calls."""

from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, cast

import pytest
from mock_bundle.hooks import MockBoth, MockBranding, MockStyle
from qtpy.QtWidgets import QApplication, QMainWindow

from redsun import (
    AsHook,
    AsPresenter,
    ConfiguresApplication,
    Declare,
    HookError,
    Serves,
    Session,
)
from redsun.qt import QtHook, QtSession
from redsun.session import BUILD_STEPS

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

pytestmark = pytest.mark.qt


class Splash:
    """Serves `during_build`, recording the span and every step inside it."""

    def __init__(self, log: list[str]) -> None:
        self.log = log

    @contextmanager
    def during_build(self, app: QApplication) -> Generator[Callable[[str], None]]:
        """Open for the whole build, collecting the name of each step."""
        self.log.append("enter")
        try:
            yield self.log.append
        finally:
            self.log.append("exit")


class Founder:
    """Serves `create_application` by handing back the application it was given."""

    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.seen: list[list[str]] = []

    def create_application(self, argv: list[str]) -> QApplication:
        """Record *argv* and return the application given at construction."""
        self.seen.append(argv)
        return self.app


class Forgetful:
    """Serves `create_application` but returns nothing, as a missing `return` would."""

    def create_application(self, argv: list[str]) -> None:
        """Return nothing."""


class Heir(ConfiguresApplication[QApplication]):
    """Serves `configure_application` by inheriting the protocol of the point."""

    def __init__(self) -> None:
        self.seen: list[QApplication] = []

    def configure_application(self, app: QApplication) -> None:
        """Record *app*."""
        self.seen.append(app)


class NotAHook:
    """Declares none of the methods any point calls."""


class ClosingPair(MockBoth):
    """Serves two points, and records its shutdown."""

    def __init__(self, closed: list[str]) -> None:
        super().__init__()
        self.closed = closed

    def shutdown(self) -> None:
        self.closed.append("pair")


class ClosingSplash:
    """Serves `during_build`, and records its shutdown."""

    def __init__(self, closed: list[str]) -> None:
        self.closed = closed

    @contextmanager
    def during_build(self, app: QApplication) -> Generator[Callable[[str], None]]:
        """Open for the whole build."""
        yield lambda step: None

    def shutdown(self) -> None:
        self.closed.append("splash")


class Unanswerable:
    """Presenter asking for something no session declares.

    A component whose constructor raises is logged and skipped, so ending a
    build part way through takes a fault the session cannot go on without.
    """

    def __init__(self, name: str, *, missing: QMainWindow) -> None:
        self.name = name


@pytest.fixture
def log() -> list[str]:
    """Return what the hook providers record, in order."""
    return []


def test_a_container_that_calls_no_point_refuses_a_hook() -> None:
    """Refuse a hook on a plain session, which calls no hook points."""

    class Headless(Session):
        configure_application: AsHook[MockStyle]

    with pytest.raises(HookError, match="it calls none"):
        Headless().build()


def test_a_hook_runs_at_the_point_its_attribute_names(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    """Run a hook at the hook point named by its attribute."""

    class App(QtSession):
        configure_application: AsHook[MockStyle]

    app = build(App)
    installed = cast("MockStyle", app.hooks[QtHook.CONFIGURE_APPLICATION])
    assert installed.seen == [qapp]


def test_the_installed_hook_points_are_logged_one_per_line(
    qapp: QApplication,
    build: Callable[..., QtSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log each hook point with a provider on a line of its own."""

    class App(QtSession):
        configure_application: AsHook[MockStyle]
        configure_main_view: AsHook[MockBranding]

    caplog.set_level(logging.DEBUG, logger="redsun")
    build(App)

    messages = [record.getMessage() for record in caplog.records]
    first = messages.index("Hooks installed at:")
    assert messages[first + 1 : first + 3] == [
        "  - configure_application",
        "  - configure_main_view",
    ]


def test_a_provider_may_inherit_the_protocol_of_its_point(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    """Accept a provider that subclasses its hook point's protocol."""

    class App(QtSession):
        configure_application: AsHook[Heir]

    app = build(App)
    installed = cast("Heir", app.hooks[QtHook.CONFIGURE_APPLICATION])
    assert installed.seen == [qapp]


def test_declare_carries_the_providers_arguments(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    """Pass Declare arguments to the hook provider's constructor."""

    class App(QtSession):
        configure_application: Annotated[AsHook[MockStyle], Declare(style="dark")]

    app = build(App)
    installed = cast("MockStyle", app.hooks[QtHook.CONFIGURE_APPLICATION])
    assert installed.style == "dark"


def test_one_annotation_serves_several_points(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    """Use one provider instance for every point listed in Serves."""

    class App(QtSession):
        pair: Annotated[
            AsHook[MockBoth],
            Serves(QtHook.CONFIGURE_APPLICATION, QtHook.CONFIGURE_MAIN_VIEW),
        ]

    app = build(App)
    hooks = app.hooks
    assert hooks[QtHook.CONFIGURE_APPLICATION] is hooks[QtHook.CONFIGURE_MAIN_VIEW]
    assert app.main_window.windowTitle() == "branded"


def test_shutdown_reaches_each_provider_once_the_last_built_first(
    qapp: QApplication,
    build: Callable[..., QtSession],
    log: list[str],
) -> None:
    """Shut down each hook provider once, in reverse build order."""
    pair = {"provider": f"{__name__}:ClosingPair", "kwargs": {"closed": log}}
    splash = {"provider": f"{__name__}:ClosingSplash", "kwargs": {"closed": log}}

    class App(QtSession):
        pass

    config = {
        "hooks": {
            "configure_application": pair,
            "configure_main_view": pair,
            "during_build": splash,
        }
    }
    app = build(App, config)
    app.shutdown()

    assert log == ["splash", "pair"]


def test_two_declarations_may_not_claim_one_point() -> None:
    """Refuse two declarations claiming the same hook point."""

    class App(QtSession):
        first: Annotated[AsHook[MockStyle], Serves(QtHook.CONFIGURE_APPLICATION)]
        second: Annotated[AsHook[MockBoth], Serves(QtHook.CONFIGURE_APPLICATION)]

    with pytest.raises(HookError, match="both claim the hook point"):
        App().build()


def test_a_point_the_container_does_not_call_is_refused() -> None:
    """Refuse a hook point the session does not call, listing the valid ones."""

    class App(QtSession):
        configure_applications: AsHook[MockStyle]

    with pytest.raises(HookError, match="expected one of: create_application"):
        App().build()


def test_a_provider_missing_the_method_is_refused() -> None:
    """Refuse a provider that does not implement its hook point's protocol."""

    class App(QtSession):
        configure_application: AsHook[NotAHook]

    with pytest.raises(HookError, match="does not implement ConfiguresApplication"):
        App().build()


def test_the_configuration_names_a_provider(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    """Install a hook provider named in the configuration, with its kwargs."""

    class App(QtSession):
        config: ClassVar[dict[str, Any]] = {
            "hooks": {
                "configure_main_view": {
                    "provider": "mock_bundle.hooks:MockBranding",
                    "kwargs": {"title": "from-file"},
                }
            }
        }

    app = build(App)
    assert app.main_window.windowTitle() == "from-file"


def test_one_point_may_not_be_named_twice_over() -> None:
    """Refuse a hook point named both on the class and in the configuration."""

    class App(QtSession):
        configure_main_view: AsHook[MockBranding]
        config: ClassVar[dict[str, Any]] = {
            "hooks": {
                "configure_main_view": {"provider": "mock_bundle.hooks:MockBranding"}
            }
        }

    with pytest.raises(HookError, match="named both on App and in the configuration"):
        App().build()


def test_an_entry_two_points_share_is_one_provider(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    """Build one provider for one configuration entry shared by two points."""
    shared = {"provider": "mock_bundle.hooks:MockBoth"}

    class App(QtSession):
        config: ClassVar[dict[str, Any]] = {
            "hooks": {"configure_application": shared, "configure_main_view": shared}
        }

    hooks = build(App).hooks

    assert hooks["configure_application"] is hooks["configure_main_view"]


def test_two_equal_entries_are_not_one_provider() -> None:
    """Refuse one provider named in two separate configuration entries."""

    class App(QtSession):
        config: ClassVar[dict[str, Any]] = {
            "hooks": {
                "configure_application": {"provider": "mock_bundle.hooks:MockBoth"},
                "configure_main_view": {"provider": "mock_bundle.hooks:MockBoth"},
            }
        }

    with pytest.raises(HookError, match="named twice"):
        App().build()


@pytest.mark.parametrize(
    ("session", "match"),
    [
        pytest.param(Session, "it calls none", id="a-session-calling-no-point"),
        pytest.param(QtSession, "expected one of", id="a-misspelled-point"),
    ],
)
def test_the_configuration_may_not_name_a_point_the_session_does_not_call(
    session: type[Session], match: str
) -> None:
    """Refuse a configured hook point the session does not call."""
    hooks = {"configure_main_vew": {"provider": "mock_bundle.hooks:MockBranding"}}

    with pytest.raises(HookError, match=match):
        session({"hooks": hooks}).build()


def test_during_build_brackets_the_build_and_names_every_step(
    qapp: QApplication,
    build: Callable[..., QtSession],
    log: list[str],
) -> None:
    """Enter the `during_build` hook once around the build and report every step."""

    class App(QtSession):
        pass

    config = {
        "hooks": {
            "during_build": {
                "provider": f"{__name__}:Splash",
                "kwargs": {"log": log},
            }
        }
    }
    build(App, config)
    assert log[0] == "enter"
    assert log[-1] == "exit"
    assert log[1:-1] == list(BUILD_STEPS)


def test_the_span_closes_on_a_failed_build(log: list[str]) -> None:
    """Exit the `during_build` hook when the build raises."""

    class App(QtSession):
        broken: AsPresenter[Unanswerable]

    config = {
        "hooks": {
            "during_build": {
                "provider": f"{__name__}:Splash",
                "kwargs": {"log": log},
            }
        }
    }
    with pytest.raises(TypeError, match="which nothing in the session provides"):
        App(config).build()
    assert log.count("enter") == 1
    assert log[-1] == "exit"


def test_create_application_is_consulted_only_with_none_running(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    build: Callable[..., QtSession],
) -> None:
    """Call the `create_application` hook only when no QApplication is running."""

    class App(QtSession):
        configure_application: AsHook[MockStyle]

    founding = {"provider": f"{__name__}:Founder", "kwargs": {"app": qapp}}
    config = {"hooks": {"create_application": founding}}
    first = build(App, config)
    unused = cast("Founder", first.hooks[QtHook.CREATE_APPLICATION])
    first.shutdown()

    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: None))
    second = build(App, config)
    founder = cast("Founder", second.hooks[QtHook.CREATE_APPLICATION])
    styler = cast("MockStyle", second.hooks[QtHook.CONFIGURE_APPLICATION])

    assert unused.seen == []
    assert founder.seen == [sys.argv]
    assert styler.seen == [qapp]


def test_a_create_application_hook_returning_nothing_is_refused(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse to build when the `create_application` hook returns no QApplication."""

    class App(QtSession):
        create_application: AsHook[Forgetful]

    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: None))
    with pytest.raises(HookError, match="'Forgetful' at 'create_application'"):
        App().build()
