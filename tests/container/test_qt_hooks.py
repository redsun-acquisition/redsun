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
def _clear_installed() -> None:
    mock_hooks.installed.clear()


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
        class TestApp(QtAppContainer):
            pass

        app = TestApp()
        app._config["hooks"] = {
            "configure_build": {"provider": "mock_pkg.hooks:RecordingHook"}
        }

        app.build()

        assert mock_hooks.installed == ["recorded"]


class TestQtHooksFromAFile:
    """Tests for a session assembled from a configuration file on disk."""

    def test_from_config_installs_the_hooks_section(self, config_path: Path) -> None:
        app = AppContainer.from_config(str(config_path / "mock_hooks_config.yaml"))

        assert isinstance(app, QtAppContainer)

        app.build()

        assert app.phases.index("custom") == app.phases.index("views") + 1
        assert mock_hooks.installed == ["custom"]

    def test_from_config_shares_an_anchored_provider(self, config_path: Path) -> None:
        app = AppContainer.from_config(
            str(config_path / "mock_shared_hook_config.yaml")
        )

        app.build()

        hook = app._hook_by_moment["configure_build"]
        assert hook is app._hook_by_moment["configure_session"]


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
