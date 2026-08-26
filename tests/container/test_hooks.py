"""Tests for container-level hook providers and the build phase registry."""

from __future__ import annotations

import logging

import pytest
from mock_pkg import hooks as mock_hooks

from redsun.containers import AppContainer, HookError

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

    def test_a_class_level_hook_configures_the_build(self) -> None:
        hook = mock_hooks.RecordingHook()

        class TestApp(AppContainer):
            hooks = (hook,)

        TestApp().build()

        assert hook.ran == ["recorded"]

    def test_a_configured_hook_configures_the_build(self) -> None:
        app = AppContainer()
        app._config["hooks"] = [{"provider": _PROVIDER}]

        app.build()

        assert "recorded" in app.phases

    def test_extra_keys_reach_the_provider_constructor(self) -> None:
        app = AppContainer()
        app._config["hooks"] = [
            {"provider": _PROVIDER, "name": "custom", "after": "views"}
        ]

        app.build()

        assert app.phases.index("custom") == app.phases.index("views") + 1

    def test_a_subclass_keeps_the_hooks_its_base_declares(self) -> None:
        base_hook = mock_hooks.RecordingHook(name="base")
        own_hook = mock_hooks.RecordingHook(name="own")

        class Base(AppContainer):
            hooks = (base_hook,)

        class Derived(Base):
            hooks = (own_hook,)

        # a list, because mypy reads the annotation off the class body and
        # cannot see the tuple __init_subclass__ puts there instead
        assert list(Derived.hooks) == [base_hook, own_hook]

    def test_class_level_hooks_run_before_configured_ones(self) -> None:
        class TestApp(AppContainer):
            hooks = (mock_hooks.RecordingHook(name="from_class"),)

        app = TestApp()
        app._config["hooks"] = [{"provider": _PROVIDER, "name": "from_config"}]

        app.build()

        assert mock_hooks.installed == ["from_class", "from_config"]

    def test_no_hooks_section_changes_nothing(self) -> None:
        assert AppContainer().build().phases == AppContainer().phases

    def test_a_provider_implementing_no_hook_protocol_is_refused(self) -> None:
        app = AppContainer()
        app._config["hooks"] = [{"provider": "mock_pkg.hooks:NoopHook"}]

        with pytest.raises(HookError, match="implements none of the hook protocols"):
            app.build()

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
        app._config["hooks"] = [{"provider": provider}]

        with pytest.raises(HookError, match=expected):
            app.build()

    def test_an_unexpected_key_names_the_provider(self) -> None:
        app = AppContainer()
        app._config["hooks"] = [{"provider": _PROVIDER, "nope": 1}]

        with pytest.raises(HookError, match="cannot construct hook provider"):
            app.build()

    @pytest.mark.parametrize("entry", [{"name": "x"}, {"provider": 1}, "a string"])
    def test_an_entry_without_a_provider_names_its_index(self, entry: object) -> None:
        app = AppContainer()
        app._config["hooks"] = [entry]  # type: ignore[list-item]

        with pytest.raises(HookError, match="hooks entry 0"):
            app.build()


class TestHookTeardown:
    """Tests for undoing what a hook installed."""

    def test_a_hook_is_torn_down_with_the_container(self) -> None:
        hook = mock_hooks.RecordingHook()

        class TestApp(AppContainer):
            hooks = (hook,)

        app = TestApp().build()
        assert mock_hooks.installed == ["recorded"]

        app.shutdown()

        assert mock_hooks.installed == []

    def test_rebuilding_leaves_one_of_what_the_hook_installed(self) -> None:
        class TestApp(AppContainer):
            hooks = (mock_hooks.RecordingHook(),)

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

            def shutdown(self) -> None:
                order.append(self.name)

        class TestApp(AppContainer):
            hooks = (
                Recorder("first"),
                Recorder("second"),
            )

        TestApp().build().shutdown()

        assert order == ["second", "first"]

    def test_a_failing_teardown_does_not_block_the_next(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        hook = mock_hooks.RecordingHook()

        class TestApp(AppContainer):
            hooks = (
                hook,
                mock_hooks.FailingShutdownHook(),
            )

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
            hooks = (NoTeardown(),)

        TestApp().build().shutdown()

    def test_a_shutdown_without_a_build_leaves_the_sequence_alone(self) -> None:
        app = AppContainer()
        app._is_built = True

        app.shutdown()

        assert app.phases == AppContainer().phases
