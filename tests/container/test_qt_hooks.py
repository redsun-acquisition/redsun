"""Tests for the Qt hook points on QtAppContainer."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, cast

import pytest
from mock_pkg import hooks as mock_hooks
from mock_pkg.view import StyleRecordingView
from qtpy.QtWidgets import QApplication

from redsun.containers import AppContainer, HookError, declare_hook, declare_view
from redsun.qt import QtAppContainer

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.qt


@pytest.fixture(autouse=True)
def _clear_open_spans() -> None:
    mock_hooks.open_spans.clear()


@pytest.fixture(autouse=True)
def _clear_stylesheet() -> None:
    app = QApplication.instance()
    if app is not None:
        cast("QApplication", app).setStyleSheet("")


class TestQtApplicationHook:
    """Tests for configuring the QApplication before the views exist."""

    def test_the_stylesheet_is_on_the_application_before_a_view_is_built(self) -> None:
        hook = mock_hooks.QtStyleHook()

        class TestApp(QtAppContainer):
            configure_application = declare_hook(hook)

            widget = declare_view(StyleRecordingView)

        app = TestApp().build()

        # the view read the stylesheet in its own __init__, so this cannot pass
        # by the hook merely having been called at some point
        view = app.views["widget"]
        assert isinstance(view, StyleRecordingView)
        assert view.stylesheet_at_build == hook.stylesheet

    def test_a_qt_point_is_refused_by_a_headless_container(self) -> None:
        with pytest.raises(HookError, match="is not a hook point it calls"):

            class TestApp(AppContainer):
                configure_application = declare_hook(mock_hooks.QtOnlyHook)

    def test_the_hooks_are_resolved_once_for_the_whole_build(self) -> None:
        hook = mock_hooks.QtStyleHook()

        class TestApp(QtAppContainer):
            configure_application = declare_hook(hook)
            configure_main_view = declare_hook(hook)

        app = TestApp().build()
        resolved = app._ensure_hooks()

        assert resolved["configure_application"] is resolved["configure_main_view"]
        assert app._ensure_hooks() is resolved


class TestQtHooksFromAFile:
    """Tests for a session assembled from a configuration file on disk."""

    def test_from_config_installs_the_hooks_section(self, config_path: Path) -> None:
        app = AppContainer.from_config(str(config_path / "mock_qt_hooks_config.yaml"))

        assert isinstance(app, QtAppContainer)

        app.build()

        hook = app._hook_by_moment["configure_application"]
        assert isinstance(hook, mock_hooks.QtStyleHook)
        assert hook.stylesheet == "QWidget { color: blue; }"
        assert cast("QApplication", QApplication.instance()).styleSheet() == (
            hook.stylesheet
        )

    def test_from_config_shares_an_anchored_provider(self, config_path: Path) -> None:
        app = AppContainer.from_config(
            str(config_path / "mock_qt_shared_hook_config.yaml")
        )

        app.build()

        hook = app._hook_by_moment["configure_application"]
        assert hook is app._hook_by_moment["configure_main_view"]


class TestQtBuildSpan:
    """Tests for the hook that wraps the whole build."""

    def test_no_hook_gives_a_span_over_a_silent_reporter(
        self, qapp: QApplication
    ) -> None:
        app = QtAppContainer()

        with app._during_build(qapp) as report:
            report("devices")

        assert mock_hooks.open_spans == []

    def test_a_declared_span_wraps_the_build_and_closes(
        self, qapp: QApplication
    ) -> None:
        span = mock_hooks.RecordingSpan()

        class TestApp(QtAppContainer):
            during_build = declare_hook(span)

        app = TestApp()

        with app._during_build(qapp) as report:
            assert mock_hooks.open_spans == ["recorded"]
            app._report = report
            app.build()

        assert span.entries == 1
        assert mock_hooks.open_spans == []
        assert span.steps == [
            "virtual container",
            "devices",
            "presenters",
            "views",
            "providers",
            "wiring",
            "injection",
        ]

    def test_a_span_closes_when_the_build_raises(self, qapp: QApplication) -> None:
        span = mock_hooks.RecordingSpan()

        class TestApp(QtAppContainer):
            during_build = declare_hook(span)

        with (
            pytest.raises(RuntimeError, match="build blew up"),
            TestApp()._during_build(qapp),
        ):
            raise RuntimeError("build blew up")

        assert mock_hooks.open_spans == []

    def test_a_provider_that_does_not_wrap_the_build_is_refused(self) -> None:
        with pytest.raises(HookError, match="does not implement WrapsBuild"):

            class TestApp(QtAppContainer):
                during_build = declare_hook(mock_hooks.QtStyleHook)


class TestQtMainViewHook:
    """Tests for configuring the main window before it is shown."""

    def test_a_hook_sees_the_window(self) -> None:
        hook = mock_hooks.QtStyleHook()

        class TestApp(QtAppContainer):
            configure_main_view = declare_hook(hook)

        app = TestApp().build()
        assert hook.window is None

        main_view = app._ensure_main_view()

        assert hook.window is main_view

    def test_one_provider_serves_the_application_and_the_window(self) -> None:
        hook = mock_hooks.QtStyleHook()

        class TestApp(QtAppContainer):
            configure_application = declare_hook(hook)
            configure_main_view = declare_hook(hook)

        app = TestApp().build()
        main_view = app._ensure_main_view()

        assert hook.window is main_view
        assert hook._app is app._qt_app

    def test_the_window_is_built_once(self) -> None:
        class TestApp(QtAppContainer):
            configure_main_view = declare_hook(mock_hooks.QtStyleHook)

        app = TestApp().build()

        assert app._ensure_main_view() is app._ensure_main_view()


class TestQtApplicationFactory:
    """Tests for the hook that supplies the QApplication itself."""

    def test_a_claimant_supplies_the_application(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # a process holding a QApplication cannot build a second one, so the
        # only way to reach the creation branch is to hide the one it has
        hook = mock_hooks.QtApplicationFactory(qapp)
        monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: None))

        class TestApp(QtAppContainer):
            create_application = declare_hook(hook)

        app = TestApp().build()

        assert hook.calls == [sys.argv]
        assert app._qt_app is qapp

    def test_a_claimant_is_skipped_when_an_application_is_running(
        self, qapp: QApplication
    ) -> None:
        hook = mock_hooks.QtApplicationFactory(qapp)

        class TestApp(QtAppContainer):
            create_application = declare_hook(hook)

        app = TestApp().build()

        assert hook.calls == []
        assert app._qt_app is qapp

    def test_the_point_named_on_the_class_and_in_the_config_is_refused(
        self, qapp: QApplication
    ) -> None:
        # refused although a running application means neither would be called:
        # two providers for one point is a configuration error whatever the
        # process holds
        class TestApp(QtAppContainer):
            create_application = declare_hook(mock_hooks.QtApplicationFactory(qapp))

        app = TestApp()
        app._config["hooks"] = {
            "create_application": {"provider": "mock_pkg.hooks:QtStyleHook"}
        }

        with pytest.raises(HookError, match="named both on TestApp"):
            app.build()


class TestQtShutdown:
    """Tests for what a Qt container leaves behind once it is shut down."""

    def test_shutdown_destroys_the_widgets_it_built(self, qapp: QApplication) -> None:
        """Releasing a widget does not end it; the container has to destroy it.

        C++ owns a widget past its last Python reference, so a container that
        only dropped its own would leave the window alive for the rest of the
        process.
        """

        class TestApp(QtAppContainer):
            ui = declare_view(StyleRecordingView)

        before = len(QApplication.topLevelWidgets())

        app = TestApp().build()
        view = app.views["ui"]
        app.shutdown()

        assert len(QApplication.topLevelWidgets()) == before
        with pytest.raises(RuntimeError):
            cast("StyleRecordingView", view).isVisible()
