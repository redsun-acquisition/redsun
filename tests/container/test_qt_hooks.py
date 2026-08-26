"""Tests for the Qt hook points on QtAppContainer."""

from __future__ import annotations

import logging
from typing import cast

import pytest
from mock_pkg import hooks as mock_hooks
from mock_pkg.view import StyleRecordingView
from qtpy.QtWidgets import QApplication

from redsun.containers import AppContainer, HookError, declare_view
from redsun.qt import QtAppContainer

pytestmark = pytest.mark.qt


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
            hooks = (hook,)

            widget = declare_view(StyleRecordingView)

        app = TestApp().build()

        # the view read the stylesheet in its own __init__, so this cannot pass
        # by the hook merely having been called at some point
        view = app.views["widget"]
        assert isinstance(view, StyleRecordingView)
        assert view.stylesheet_at_build == hook.stylesheet

    def test_a_qt_only_hook_is_accepted_by_a_qt_container(self) -> None:
        class TestApp(QtAppContainer):
            hooks = (mock_hooks.QtStyleHook(),)

        assert TestApp().build().is_built

    def test_a_hook_with_only_qt_points_is_refused_by_a_headless_container(
        self,
    ) -> None:
        class TestApp(AppContainer):
            hooks = (mock_hooks.QtOnlyHook(),)

        with pytest.raises(HookError, match="implements none of the hook protocols"):
            TestApp().build()

    def test_a_hook_point_the_container_never_calls_is_warned_about(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # QtStyleHook also implements shutdown, which a headless container does
        # call, so it resolves - but its Qt points silently would not run
        class TestApp(AppContainer):
            hooks = (mock_hooks.QtStyleHook(),)

        with caplog.at_level(logging.WARNING, logger="redsun"):
            TestApp().build()

        assert "ConfiguresApplication" in caplog.text
        assert "never calls" in caplog.text

    def test_a_qt_container_warns_about_nothing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class TestApp(QtAppContainer):
            hooks = (mock_hooks.QtStyleHook(),)

        with caplog.at_level(logging.WARNING, logger="redsun"):
            TestApp().build()

        assert "never calls" not in caplog.text

    def test_the_hooks_are_resolved_once_for_the_whole_build(self) -> None:
        class TestApp(QtAppContainer):
            pass

        app = TestApp()
        app._config["hooks"] = [{"provider": "mock_pkg.hooks:RecordingHook"}]

        app.build()

        assert mock_hooks.installed == ["recorded"]


class TestQtMainViewHook:
    """Tests for configuring the main window before it is shown."""

    def test_a_hook_sees_the_window(self) -> None:
        hook = mock_hooks.QtStyleHook()

        class TestApp(QtAppContainer):
            hooks = (hook,)

        app = TestApp().build()
        assert hook.window is None

        main_view = app._ensure_main_view()

        assert hook.window is main_view

    def test_the_window_is_built_once(self) -> None:
        class TestApp(QtAppContainer):
            hooks = (mock_hooks.QtStyleHook(),)

        app = TestApp().build()

        assert app._ensure_main_view() is app._ensure_main_view()
