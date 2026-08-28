"""Tests for container-level hook providers and the build phase registry."""

from __future__ import annotations

import gc
import logging
import weakref
from typing import TYPE_CHECKING

import pytest
import yaml
from mock_pkg import hooks as mock_hooks
from mock_pkg.device import MyMotor

from redsun.containers import (
    AppContainer,
    HookError,
    declare_device,
    declare_hook,
)

if TYPE_CHECKING:
    from pathlib import Path

_PROVIDER = "mock_pkg.hooks:RecordingHook"


@pytest.fixture(autouse=True)
def _clear_installed() -> None:
    mock_hooks.installed.clear()


class TestPhaseRegistry:
    """Tests for the public build phase API."""

    def test_a_registered_phase_runs_where_it_was_placed(self) -> None:
        calls: list[str] = []
        app = AppContainer()
        app.register_phase("mine", lambda: calls.append("mine"), after="devices")

        assert app.phases.index("mine") == app.phases.index("devices") + 1

        app.build()

        assert calls == ["mine"]

    def test_phases_reports_the_built_in_sequence(self) -> None:
        assert AppContainer().phases == [
            "virtual_container",
            "devices",
            "presenters",
            "views",
            "providers",
            "wiring",
            "injection",
        ]

    def test_a_registered_phase_can_be_removed_again(self) -> None:
        app = AppContainer()
        app.register_phase("mine", lambda: None, after="views")
        app.unregister_phase("mine")

        assert app.phases == AppContainer().phases

    @pytest.mark.parametrize("name", ["devices", "wiring", "virtual_container"])
    def test_a_built_in_phase_cannot_be_removed(self, name: str) -> None:
        with pytest.raises(ValueError, match="built in and cannot be removed"):
            AppContainer().unregister_phase(name)

    def test_registering_after_an_unknown_phase_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown phase 'nope'"):
            AppContainer().register_phase("mine", lambda: None, after="nope")

    def test_registering_a_known_name_twice_is_refused(self) -> None:
        app = AppContainer()
        with pytest.raises(ValueError, match="already registered"):
            app.register_phase("devices", lambda: None, after="views")

    def test_removing_an_unregistered_phase_is_refused(self) -> None:
        with pytest.raises(ValueError, match="is not registered"):
            AppContainer().unregister_phase("mine")

    @pytest.mark.parametrize("action", ["register", "unregister"])
    def test_the_sequence_is_frozen_once_built(self, action: str) -> None:
        app = AppContainer().build()

        with pytest.raises(RuntimeError, match="after the container is built"):
            if action == "register":
                app.register_phase("mine", lambda: None, after="devices")
            else:
                app.unregister_phase("mine")

    def test_a_registered_phase_belongs_to_one_container(self) -> None:
        app = AppContainer()
        app.register_phase("mine", lambda: None, after="devices")

        assert "mine" not in AppContainer().phases


class TestHookResolution:
    """Tests for turning the 'hooks' configuration section into providers."""

    def test_a_declared_hook_configures_the_build(self) -> None:
        hook = mock_hooks.RecordingHook()

        class TestApp(AppContainer):
            configure_build = declare_hook(hook)

        TestApp().build()

        assert hook.ran == ["recorded"]

    def test_a_declared_class_is_constructed_with_its_keywords(self) -> None:
        class TestApp(AppContainer):
            configure_build = declare_hook(
                mock_hooks.RecordingHook, name="custom", after="views"
            )

        app = TestApp().build()

        assert app.phases.index("custom") == app.phases.index("views") + 1

    def test_a_configured_hook_configures_the_build(self) -> None:
        app = AppContainer()
        app._config["hooks"] = {"configure_build": {"provider": _PROVIDER}}

        app.build()

        assert "recorded" in app.phases

    def test_kwargs_reach_the_provider_constructor(self) -> None:
        app = AppContainer()
        app._config["hooks"] = {
            "configure_build": {
                "provider": _PROVIDER,
                "kwargs": {"name": "custom", "after": "views"},
            }
        }

        app.build()

        assert app.phases.index("custom") == app.phases.index("views") + 1

    def test_a_subclass_keeps_the_hooks_its_base_declares(self) -> None:
        base_hook = mock_hooks.RecordingHook(name="base")
        own_hook = mock_hooks.SessionHook()

        class Base(AppContainer):
            configure_build = declare_hook(base_hook)

        class Derived(Base):
            configure_session = declare_hook(own_hook)

        assert Derived._hook_providers == {
            "configure_build": base_hook,
            "configure_session": own_hook,
        }

    def test_a_subclass_replaces_a_point_its_base_declared(self) -> None:
        own_hook = mock_hooks.RecordingHook(name="own")

        class Base(AppContainer):
            configure_build = declare_hook(mock_hooks.RecordingHook, name="base")

        class Derived(Base):
            configure_build = declare_hook(own_hook)

        Derived().build()

        assert mock_hooks.installed == ["own"]

    def test_a_declared_point_and_a_configured_one_run_together(self) -> None:
        session_hook = mock_hooks.SessionHook()

        class TestApp(AppContainer):
            configure_session = declare_hook(session_hook)

        app = TestApp()
        app._config["hooks"] = {"configure_build": {"provider": _PROVIDER}}

        app.build()

        assert mock_hooks.installed == ["recorded"]
        assert session_hook.saw is not None

    def test_a_point_named_twice_is_refused(self) -> None:
        class TestApp(AppContainer):
            configure_build = declare_hook(mock_hooks.RecordingHook)

        app = TestApp()
        app._config["hooks"] = {"configure_build": {"provider": _PROVIDER}}

        with pytest.raises(HookError, match="named both on TestApp"):
            app.build()

    def test_no_hooks_section_changes_nothing(self) -> None:
        assert AppContainer().build().phases == AppContainer().phases

    def test_a_provider_that_does_not_serve_its_point_is_refused(self) -> None:
        app = AppContainer()
        app._config["hooks"] = {
            "configure_build": {"provider": "mock_pkg.hooks:NoopHook"}
        }

        with pytest.raises(HookError, match="does not implement ConfiguresBuild"):
            app.build()

    def test_a_declared_provider_that_does_not_serve_its_point_is_refused(self) -> None:
        with pytest.raises(HookError, match="does not implement ConfiguresBuild"):

            class TestApp(AppContainer):
                configure_build = declare_hook(mock_hooks.NoopHook)

    def test_a_point_the_container_never_calls_is_refused(self) -> None:
        app = AppContainer()
        app._config["hooks"] = {"configure_application": {"provider": _PROVIDER}}

        with pytest.raises(HookError, match="is not a hook point AppContainer calls"):
            app.build()

    def test_a_declared_point_the_container_never_calls_is_refused(self) -> None:
        with pytest.raises(HookError, match="is not a hook point it calls"):

            class TestApp(AppContainer):
                configure_application = declare_hook(mock_hooks.QtOnlyHook)

    @pytest.mark.parametrize(
        ("provider", "expected"),
        [
            ("mock_pkg.hooks", "not a class path"),
            ("mock_pkg.nope:Hook", "cannot import"),
            ("mock_pkg.hooks:Missing", "cannot import"),
            ("mock_pkg.hooks:installed", "is not a class"),
        ],
    )
    def test_an_unresolvable_provider_names_what_is_wrong(
        self, provider: str, expected: str
    ) -> None:
        app = AppContainer()
        app._config["hooks"] = {"configure_build": {"provider": provider}}

        with pytest.raises(HookError, match=expected):
            app.build()

    def test_a_keyword_the_provider_rejects_names_the_provider(self) -> None:
        app = AppContainer()
        app._config["hooks"] = {
            "configure_build": {"provider": _PROVIDER, "kwargs": {"nope": 1}}
        }

        with pytest.raises(HookError, match="cannot construct hook provider"):
            app.build()

    def test_a_declared_keyword_the_provider_rejects_names_the_point(self) -> None:
        with pytest.raises(HookError, match="declared at 'configure_build'"):

            class TestApp(AppContainer):
                configure_build = declare_hook(mock_hooks.RecordingHook, nope=1)

    def test_keywords_beside_the_provider_are_refused(self) -> None:
        app = AppContainer()
        app._config["hooks"] = {
            "configure_build": {"provider": _PROVIDER, "name": "custom"}
        }

        with pytest.raises(HookError, match="unknown key"):
            app.build()

    @pytest.mark.parametrize(
        "entry",
        [
            {"kwargs": {}},
            {"provider": 1},
            "a string",
            {"provider": _PROVIDER, "kwargs": 1},
        ],
    )
    def test_a_malformed_entry_names_its_hook_point(self, entry: object) -> None:
        app = AppContainer()
        app._config["hooks"] = {"configure_build": entry}  # type: ignore[dict-item]

        with pytest.raises(HookError, match="'configure_build'"):
            app.build()

    def test_declaring_keywords_for_a_built_provider_is_refused(self) -> None:
        with pytest.raises(TypeError, match="already constructed"):
            declare_hook(mock_hooks.RecordingHook(), name="nope")  # type: ignore[call-overload]


class TestSharedProviders:
    """Tests for one provider serving more than one hook point."""

    def test_an_anchored_entry_gives_one_provider_to_both_points(self) -> None:
        app = AppContainer()
        app._config["hooks"] = yaml.safe_load(
            """
            configure_build: &shared
              provider: mock_pkg.hooks:BothPointsHook
            configure_session: *shared
            """
        )

        app.build()

        hook = app._hook_by_moment["configure_build"]
        assert hook is app._hook_by_moment["configure_session"]
        assert isinstance(hook, mock_hooks.BothPointsHook)
        assert hook.seen == ["build", "session"]

    def test_a_declared_instance_serves_both_points(self) -> None:
        hook = mock_hooks.BothPointsHook()

        class TestApp(AppContainer):
            configure_build = declare_hook(hook)
            configure_session = declare_hook(hook)

        TestApp().build()

        assert hook.seen == ["build", "session"]

    def test_two_indistinguishable_entries_are_refused(self) -> None:
        app = AppContainer()
        app._config["hooks"] = {
            "configure_build": {"provider": "mock_pkg.hooks:BothPointsHook"},
            "configure_session": {"provider": "mock_pkg.hooks:BothPointsHook"},
        }

        with pytest.raises(HookError, match="is named twice"):
            app.build()

    def test_two_entries_with_different_keywords_build_two_providers(self) -> None:
        app = AppContainer()
        app._config["hooks"] = {
            "configure_build": {
                "provider": "mock_pkg.hooks:BothPointsHook",
                "kwargs": {"name": "first"},
            },
            "configure_session": {
                "provider": "mock_pkg.hooks:BothPointsHook",
                "kwargs": {"name": "second"},
            },
        }

        app.build()

        assert (
            app._hook_by_moment["configure_build"]
            is not app._hook_by_moment["configure_session"]
        )

    def test_a_shared_provider_is_torn_down_once(self) -> None:
        hook = mock_hooks.BothPointsHook()

        class TestApp(AppContainer):
            configure_build = declare_hook(hook)
            configure_session = declare_hook(hook)

        TestApp().build().shutdown()

        assert hook.teardowns == 1


class TestHooksFromAFile:
    """Tests for the 'hooks' section read from a configuration file on disk."""

    def test_a_declarative_container_reads_the_hooks_section(
        self, config_path: Path
    ) -> None:
        class TestApp(AppContainer, config=config_path / "mock_hooks_config.yaml"):
            pass

        app = TestApp().build()

        assert app.phases.index("custom") == app.phases.index("views") + 1
        assert mock_hooks.installed == ["custom"]

    def test_an_anchored_entry_read_from_a_file_gives_one_provider(
        self, config_path: Path
    ) -> None:
        class TestApp(
            AppContainer, config=config_path / "mock_shared_hook_config.yaml"
        ):
            pass

        app = TestApp().build()

        hook = app._hook_by_moment["configure_build"]
        assert hook is app._hook_by_moment["configure_session"]
        assert isinstance(hook, mock_hooks.BothPointsHook)
        assert hook.name == "shared"
        assert hook.seen == ["build", "session"]

    def test_a_shared_provider_read_from_a_file_is_torn_down_once(
        self, config_path: Path
    ) -> None:
        class TestApp(
            AppContainer, config=config_path / "mock_shared_hook_config.yaml"
        ):
            pass

        app = TestApp().build()
        hook = app._hook_by_moment["configure_build"]
        assert isinstance(hook, mock_hooks.BothPointsHook)

        app.shutdown()

        assert hook.teardowns == 1


class TestHookTeardown:
    """Tests for undoing what a hook installed."""

    def test_a_hook_is_torn_down_with_the_container(self) -> None:
        hook = mock_hooks.RecordingHook()

        class TestApp(AppContainer):
            configure_build = declare_hook(hook)

        app = TestApp().build()
        assert mock_hooks.installed == ["recorded"]

        app.shutdown()

        assert mock_hooks.installed == []

    def test_rebuilding_leaves_one_of_what_the_hook_installed(self) -> None:
        class TestApp(AppContainer):
            configure_build = declare_hook(mock_hooks.RecordingHook)

        app = TestApp()
        app.build()
        app.shutdown()
        app.build()

        assert mock_hooks.installed == ["recorded"]
        assert app.phases.count("recorded") == 1

    def test_a_phase_registered_by_hand_survives_a_rebuild(self) -> None:
        app = AppContainer()
        app.register_phase("mine", lambda: None, after="devices")

        app.build()
        app.shutdown()

        assert "mine" in app.phases

    def test_hooks_are_torn_down_in_reverse_order(self) -> None:
        order: list[str] = []

        class Recorder:
            def __init__(self, name: str) -> None:
                self.name = name

            def configure_build(self, container: AppContainer) -> None:
                pass

            def configure_session(self, container: AppContainer) -> None:
                pass

            def shutdown(self) -> None:
                order.append(self.name)

        class TestApp(AppContainer):
            configure_build = declare_hook(Recorder("first"))
            configure_session = declare_hook(Recorder("second"))

        TestApp().build().shutdown()

        assert order == ["second", "first"]

    def test_a_failing_teardown_does_not_block_the_next(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        hook = mock_hooks.RecordingHook()

        class TestApp(AppContainer):
            configure_build = declare_hook(hook)
            configure_session = declare_hook(mock_hooks.FailingShutdownHook)

        app = TestApp().build()
        with caplog.at_level(logging.ERROR, logger="redsun"):
            app.shutdown()

        assert "teardown blew up" in caplog.text
        assert mock_hooks.installed == []

    def test_a_hook_without_a_teardown_is_skipped(self) -> None:
        class NoTeardown:
            def configure_build(self, container: AppContainer) -> None:
                pass

        class TestApp(AppContainer):
            configure_build = declare_hook(NoTeardown())

        TestApp().build().shutdown()

    def test_a_shutdown_without_a_build_leaves_the_sequence_alone(self) -> None:
        app = AppContainer()
        app._is_built = True

        app.shutdown()

        assert app.phases == AppContainer().phases


class TestSessionMoment:
    """Tests for the after-the-session-is-built moment and its progress signal."""

    def test_a_session_hook_sees_a_finished_container(self) -> None:
        hook = mock_hooks.SessionHook()

        class TestApp(AppContainer):
            configure_session = declare_hook(hook)

            motor = declare_device(
                MyMotor,
                axis=["X"],
                step_size={"X": 0.1},
                egu="mm",
                integer=1,
                floating=1.0,
                string="s",
            )

        TestApp().build()

        assert hook.saw == {"devices": 1, "presenters": 0, "views": 0}

    def test_the_phase_signal_reports_every_phase_in_order(self) -> None:
        watcher = mock_hooks.PhaseWatcher()

        class TestApp(AppContainer):
            configure_build = declare_hook(watcher)

        app = TestApp().build()

        assert watcher.seen == app.phases

    def test_the_phase_signal_reports_a_registered_phase_too(self) -> None:
        seen: list[str] = []
        app = AppContainer()
        app.sig_phase_complete.connect(seen.append)
        app.register_phase("mine", lambda: None, after="devices")

        app.build()

        assert seen == app.phases
        assert "mine" in seen

    def test_the_signal_is_per_container(self) -> None:
        first, second = AppContainer(), AppContainer()

        assert first.sig_phase_complete is not second.sig_phase_complete

    def test_a_container_is_collected_once_dropped(self) -> None:
        # psygnal refers to a signal's owner weakly, and falls back to a strong
        # reference when it cannot. A slotted class cannot be referred to
        # weakly unless __weakref__ is one of its slots, and on that fallback
        # no container is ever collected.
        gc.collect()
        cache = AppContainer.__dict__["sig_phase_complete"]._signal_instance_cache
        before = len(cache)

        app = AppContainer()
        app.sig_phase_complete.connect(lambda _: None)
        ref = weakref.ref(app)
        assert len(cache) == before + 1

        del app
        gc.collect()

        assert ref() is None
        assert len(cache) == before
