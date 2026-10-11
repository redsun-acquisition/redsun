"""Tests for the hook points a session calls."""

from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, cast

import pytest
from mock_bundle.hooks import MockBoth, MockBranding, MockStyle
from ophyd_async.core import Device
from qtpy.QtWidgets import QApplication, QMainWindow, QWidget

from redsun import (
    AsDevice,
    AsHook,
    AsPresenter,
    AsView,
    BuildError,
    ConfiguresApplication,
    Declare,
    HookError,
    Placement,
    Serves,
    Session,
)
from redsun.qt import Dock, QtHook, QtSession
from redsun.qt.styles.napari import NapariStyle

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from redsun.testing import BuildSession

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


class Gauge(Device):
    """Device recording its construction."""

    def __init__(self, name: str, log: list[str]) -> None:
        log.append("device built")
        super().__init__(name=name)


class Tracker:
    """Presenter recording its construction."""

    def __init__(self, name: str, log: list[str]) -> None:
        self.name = name
        log.append("presenter built")


class Board(QWidget):
    """View recording its construction."""

    placement: Placement = Dock("left")

    def __init__(self, name: str, parent: QWidget, log: list[str]) -> None:
        super().__init__(parent)
        self.name = name
        log.append("view built")


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


class Notes:
    """Writes its note to the list it is handed when the application is configured."""

    def __init__(self, note: str, log: list[str]) -> None:
        self.note = note
        self.log = log

    def configure_application(self, app: QApplication) -> None:
        self.log.append(self.note)


class Signs:
    """Adds its note to the `notes` the main window carries."""

    def __init__(self, note: str) -> None:
        self.note = note

    def configure_main_view(self, view: QMainWindow) -> None:
        view.setProperty("notes", [*(view.property("notes") or []), self.note])


class Breaks:
    """Raises at `configure_application`, and records every call it gets."""

    def __init__(self, log: list[str]) -> None:
        self.log = log

    def configure_application(self, app: QApplication) -> None:
        self.log.append("breaks at the application")
        raise RuntimeError("no stylesheet today")

    def configure_main_view(self, view: QMainWindow) -> None:
        self.log.append("breaks at the window")

    def shutdown(self) -> None:
        self.log.append("breaks shut down")


class Unbuildable:
    """Cannot be constructed."""

    def __init__(self) -> None:
        raise RuntimeError("no licence found")

    def configure_application(self, app: QApplication) -> None:
        """Never reached."""

    def create_application(self, argv: list[str]) -> QApplication:
        raise AssertionError("never built")


class CannotAnswer:
    """Raises when asked whether the session may close, recording that it was asked."""

    def __init__(self, log: list[str]) -> None:
        self.log = log

    def confirm_close(self) -> bool:
        self.log.append("asked")
        raise RuntimeError("no answer")


class BrokenSplash:
    """Serves `during_build` with a reporter that raises, recording its span."""

    def __init__(self, log: list[str]) -> None:
        self.log = log

    @contextmanager
    def during_build(self, app: QApplication) -> Generator[Callable[[str], None]]:
        self.log.append("broken enter")

        def report(step: str) -> None:
            self.log.append(f"broken {step}")
            raise RuntimeError("no progress bar")

        try:
            yield report
        finally:
            self.log.append("broken exit")


class AlwaysRefuses:
    """Answers the close question with a refusal."""

    def confirm_close(self) -> bool:
        return False


class Answers:
    """Answers the close question with what it was built with."""

    def __init__(self, answer: bool = True) -> None:
        self.answer = answer

    def confirm_close(self) -> bool:
        return self.answer


class ClosingPair(MockBoth):  # type: ignore[misc]
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


class StyledApp(QtSession):
    configure_application: AsHook[MockStyle]


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
    build: BuildSession,
) -> None:
    """Run a hook at the hook point named by its attribute."""
    app = build(StyledApp)
    (provider,) = app.hooks[QtHook.CONFIGURE_APPLICATION]
    installed = cast("MockStyle", provider)
    assert installed.seen == [qapp]


def test_the_installed_hook_points_are_logged_one_per_line(
    qapp: QApplication,
    build: BuildSession,
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
    build: BuildSession,
) -> None:
    """Accept a provider that subclasses its hook point's protocol."""

    class App(QtSession):
        configure_application: AsHook[Heir]

    app = build(App)
    (provider,) = app.hooks[QtHook.CONFIGURE_APPLICATION]
    installed = cast("Heir", provider)
    assert installed.seen == [qapp]


def test_declare_carries_the_providers_arguments(
    qapp: QApplication,
    build: BuildSession,
) -> None:
    """Pass Declare arguments to the hook provider's constructor."""

    class App(QtSession):
        configure_application: Annotated[AsHook[MockStyle], Declare(style="dark")]

    app = build(App)
    (provider,) = app.hooks[QtHook.CONFIGURE_APPLICATION]
    installed = cast("MockStyle", provider)
    assert installed.style == "dark"


def test_one_annotation_serves_several_points(
    qapp: QApplication,
    build: BuildSession,
) -> None:
    """Use one provider instance for every point listed in Serves."""

    class App(QtSession):
        pair: Annotated[
            AsHook[MockBoth],
            Serves(QtHook.CONFIGURE_APPLICATION, QtHook.CONFIGURE_MAIN_VIEW),
        ]

    app = build(App)
    hooks = app.hooks
    (styled,) = hooks[QtHook.CONFIGURE_APPLICATION]
    (branded,) = hooks[QtHook.CONFIGURE_MAIN_VIEW]
    assert styled is branded
    assert app.main_window.windowTitle() == "branded"


def test_shutdown_reaches_each_provider_once_the_last_built_first(
    qapp: QApplication,
    build: BuildSession,
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
        first: Annotated[AsHook[Answers], Serves(QtHook.CONFIRM_CLOSE)]
        second: Annotated[AsHook[AlwaysRefuses], Serves(QtHook.CONFIRM_CLOSE)]

    with pytest.raises(HookError, match="takes one provider"):
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


def test_a_points_providers_run_in_order_the_class_first(
    qapp: QApplication, build: BuildSession
) -> None:
    """Run every provider of a point: the class's in declaration order, then the file's as listed."""

    class App(QtSession):
        configure_main_view: Annotated[AsHook[Signs], Declare(note="class first")]
        second: Annotated[
            AsHook[Signs],
            Serves(QtHook.CONFIGURE_MAIN_VIEW),
            Declare(note="class second"),
        ]

    listed = [
        {"provider": f"{__name__}:Signs", "kwargs": {"note": note}}
        for note in ("file first", "file second")
    ]
    app = build(App, {"hooks": {"configure_main_view": listed}})

    order = ["class first", "class second", "file first", "file second"]
    assert app.main_window.property("notes") == order
    installed = app.hooks[QtHook.CONFIGURE_MAIN_VIEW]
    assert [cast("Signs", provider).note for provider in installed] == order


def test_a_session_maps_every_point_it_calls(
    qapp: QApplication, build: BuildSession
) -> None:
    """Map every hook point to its providers, none included."""
    assert build(QtSession).hooks == {point: () for point in QtHook}


def test_a_point_taking_one_provider_refuses_a_second() -> None:
    """Refuse a second provider at a point whose answer the session uses."""
    listed = [
        {"provider": f"{__name__}:Answers"},
        {"provider": f"{__name__}:Answers", "kwargs": {"answer": False}},
    ]

    with pytest.raises(HookError, match="takes one provider"):
        QtSession({"hooks": {"confirm_close": listed}}).build()


def test_a_provider_that_raises_is_skipped_and_the_rest_run(
    qapp: QApplication,
    build: BuildSession,
    log: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Skip a provider whose hook raises: log it, run the others, and call it nowhere else."""
    broken = {"provider": f"{__name__}:Breaks", "kwargs": {"log": log}}
    after = {
        "provider": f"{__name__}:Notes",
        "kwargs": {"note": "after it", "log": log},
    }
    hooks = {"configure_application": [broken, after], "configure_main_view": broken}

    with caplog.at_level(logging.WARNING, logger="redsun"):
        app = build(QtSession, {"hooks": hooks})
        at_the_application = app.hooks[QtHook.CONFIGURE_APPLICATION]
        at_the_window = app.hooks[QtHook.CONFIGURE_MAIN_VIEW]
        app.shutdown()

    assert log == ["breaks at the application", "after it"]
    assert [type(provider) for provider in at_the_application] == [Notes]
    assert at_the_window == ()
    assert "no stylesheet today" in caplog.text
    assert "Hooks skipped: Breaks" in caplog.text


def test_a_provider_that_cannot_be_built_is_skipped(
    qapp: QApplication, build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Skip a provider of a point taking several when it cannot be constructed."""
    hooks = {"configure_application": {"provider": f"{__name__}:Unbuildable"}}

    with caplog.at_level(logging.WARNING, logger="redsun"):
        app = build(QtSession, {"hooks": hooks})

    assert app.hooks[QtHook.CONFIGURE_APPLICATION] == ()
    assert "no licence found" in caplog.text


def test_a_failed_application_provider_stops_the_build(qapp: QApplication) -> None:
    """Stop the build when the provider of `create_application` cannot be built."""
    hooks = {"create_application": {"provider": f"{__name__}:Unbuildable"}}

    with pytest.raises(HookError, match="create_application"):
        QtSession({"hooks": hooks}).build()


def test_a_strict_session_stops_on_a_skipped_hook(
    qapp: QApplication, log: list[str]
) -> None:
    """Stop a strict build that skipped a hook provider, naming it."""
    hooks = {
        "configure_application": {
            "provider": f"{__name__}:Breaks",
            "kwargs": {"log": log},
        }
    }

    with pytest.raises(BuildError, match="Breaks"):
        QtSession({"strict": True, "hooks": hooks}).build()


def test_a_close_provider_that_raises_gives_way_to_the_sessions_own_rule(
    qapp: QApplication,
    build: BuildSession,
    log: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log a `confirm_close` provider that raises, close by the session's own rule, and ask it no more."""
    hooks = {
        "confirm_close": {
            "provider": f"{__name__}:CannotAnswer",
            "kwargs": {"log": log},
        }
    }
    app = build(QtSession, {"hooks": hooks})

    with caplog.at_level(logging.ERROR, logger="redsun"):
        closed = app.main_window.close()

    assert closed
    assert log == ["asked"]
    assert "no answer" in caplog.text
    assert app.hooks[QtHook.CONFIRM_CLOSE] == ()


def test_a_span_whose_reporter_raises_is_left_and_reported_to_no_more(
    qapp: QApplication, build: BuildSession, log: list[str]
) -> None:
    """Finish the build when a `during_build` reporter raises: report to it no more, and still leave its span."""
    listed = [
        {"provider": f"{__name__}:BrokenSplash", "kwargs": {"log": log}},
        {"provider": f"{__name__}:Splash", "kwargs": {"log": log}},
    ]

    build(QtSession, {"hooks": {"during_build": listed}})

    broken = [entry for entry in log if entry.startswith("broken")]
    assert broken == ["broken enter", "broken services", "broken exit"]
    assert "report" in log
    assert log.count("exit") == 1


def test_the_configuration_names_a_provider(
    qapp: QApplication,
    build: BuildSession,
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
        confirm_close: AsHook[Answers]
        config: ClassVar[dict[str, Any]] = {
            "hooks": {"confirm_close": {"provider": f"{__name__}:Answers"}}
        }

    with pytest.raises(HookError, match="takes one provider"):
        App().build()


def test_an_entry_two_points_share_is_one_provider(
    qapp: QApplication,
    build: BuildSession,
) -> None:
    """Build one provider for one configuration entry shared by two points."""
    shared = {"provider": "mock_bundle.hooks:MockBoth"}

    class App(QtSession):
        config: ClassVar[dict[str, Any]] = {
            "hooks": {"configure_application": shared, "configure_main_view": shared}
        }

    hooks = build(App).hooks

    (styled,) = hooks["configure_application"]
    (branded,) = hooks["configure_main_view"]
    assert styled is branded


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
    "entry", ["napari", {"provider": "napari"}], ids=["bare-name", "provider"]
)
def test_a_short_name_installs_the_built_in_provider(
    qapp: QApplication,
    build: BuildSession,
    unstyled: None,
    entry: str | dict[str, str],
) -> None:
    """Install the built-in provider an entry names by its short name, alone or as `provider`."""
    hooks = build(QtSession, {"hooks": {"configure_application": entry}}).hooks

    (installed,) = hooks[QtHook.CONFIGURE_APPLICATION]
    assert isinstance(installed, NapariStyle)


@pytest.mark.parametrize(
    "other",
    ["napari", "redsun.qt.styles.napari:NapariStyle"],
    ids=["short-name", "class-path"],
)
def test_one_short_name_at_two_points_is_named_twice(other: str) -> None:
    """Refuse a short name at two points, or with its class path, as one provider named twice."""
    hooks = {"configure_application": "napari", "configure_main_view": other}

    with pytest.raises(HookError, match="named twice"):
        QtSession({"hooks": hooks}).build()


def test_a_short_name_named_twice_is_shown_as_written() -> None:
    """Show a short name named twice as it was written, with the form that shares one provider."""
    hooks = {"configure_application": "napari", "configure_main_view": "napari"}

    with pytest.raises(HookError, match=r"'napari' is named twice.*provider: napari"):
        QtSession({"hooks": hooks}).build()


def test_an_unknown_short_name_is_refused_with_the_names_there_are() -> None:
    """Refuse a short name the manifest does not list, naming the ones it does."""
    hooks = {"configure_application": "nope"}

    with pytest.raises(HookError, match=r"unknown hook provider 'nope'.*napari"):
        QtSession({"hooks": hooks}).build()


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


def test_the_build_runs_its_steps_in_order(
    qapp: QApplication,
    build: BuildSession,
    log: list[str],
) -> None:
    """Report each step to `during_build` as it starts, and build each layer in it."""

    class App(QtSession):
        gauge: AsDevice[Gauge]
        tracker: AsPresenter[Tracker]
        board: AsView[Board]

    config = {
        "devices": {"gauge": {"log": log}},
        "presenters": {"tracker": {"log": log}},
        "views": {"board": {"log": log}},
        "hooks": {
            "during_build": {
                "provider": f"{__name__}:Splash",
                "kwargs": {"log": log},
            }
        },
    }
    build(App, config)
    assert log == [
        "enter",
        "services",
        "devices",
        "device built",
        "connect",
        "registry",
        "presenters",
        "presenter built",
        "views",
        "view built",
        "setup",
        "seal",
        "wiring",
        "presentation",
        "report",
        "exit",
    ]


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
    build: BuildSession,
) -> None:
    """Call the `create_application` hook only when no QApplication is running."""
    founding = {"provider": f"{__name__}:Founder", "kwargs": {"app": qapp}}
    config = {"hooks": {"create_application": founding}}
    first = build(StyledApp, config)
    unused = cast("Founder", first.hooks[QtHook.CREATE_APPLICATION][0])
    first.shutdown()

    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: None))
    second = build(StyledApp, config)
    founder = cast("Founder", second.hooks[QtHook.CREATE_APPLICATION][0])
    styler = cast("MockStyle", second.hooks[QtHook.CONFIGURE_APPLICATION][0])

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
