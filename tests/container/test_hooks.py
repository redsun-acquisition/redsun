"""Tests for container-level hook providers.

`AppContainer` calls no hook point of its own: every moment a hook can act at
belongs to a toolkit. The machinery that turns a declaration or a ``hooks``
section into providers is toolkit-neutral, so it is exercised here through
`GreetingContainer`, a container declaring two points of its own - which is
also what a container for a new toolkit does.
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

import pytest
import yaml
from mock_pkg import hooks as mock_hooks

from redsun.containers import (
    AppContainer,
    HookError,
    declare_hook,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path
    from typing import Self

_PROVIDER = "mock_pkg.hooks:GreetingHook"


@runtime_checkable
class Greets(Protocol):
    """Runs as the build starts."""

    @abstractmethod
    def greet(self, container: AppContainer) -> None: ...


@runtime_checkable
class Farewells(Protocol):
    """Runs as the build ends."""

    @abstractmethod
    def farewell(self, container: AppContainer) -> None: ...


class GreetingContainer(AppContainer):
    """A container with two hook points of its own, standing in for a toolkit."""

    __slots__ = ()

    _hook_keys: ClassVar[Mapping[str, type]] = {
        "greet": Greets,
        "farewell": Farewells,
    }

    def build(self) -> Self:
        hooks = self._ensure_hooks()
        greeter = hooks.get("greet")
        if isinstance(greeter, Greets):
            greeter.greet(self)
        super().build()
        leaver = hooks.get("farewell")
        if isinstance(leaver, Farewells):
            leaver.farewell(self)
        return self


@pytest.fixture(autouse=True)
def _clear_greeted() -> None:
    mock_hooks.greeted.clear()


class TestPointsBelongToTheContainer:
    """Tests that a container answers only for the points it declares."""

    def test_the_base_container_calls_no_hook_point(self) -> None:
        assert AppContainer._hook_keys == {}

    def test_a_hooks_section_on_the_base_container_is_refused(self) -> None:
        app = AppContainer()
        app._config["hooks"] = {"greet": {"provider": _PROVIDER}}

        with pytest.raises(HookError, match="is not a hook point AppContainer calls"):
            app.build()

    def test_a_container_calling_none_says_so_rather_than_listing_nothing(
        self,
    ) -> None:
        app = AppContainer()
        app._config["hooks"] = {"greet": {"provider": _PROVIDER}}

        with pytest.raises(HookError, match="it calls none") as configured:
            app.build()

        with pytest.raises(HookError, match="it calls none") as declared:

            class TestApp(AppContainer):
                greet = declare_hook(mock_hooks.GreetingHook)

        for raised in (configured, declared):
            assert "expected one of" not in str(raised.value)
            assert "QtAppContainer" in str(raised.value)

    def test_a_point_the_container_never_calls_is_refused(self) -> None:
        app = GreetingContainer()
        app._config["hooks"] = {"configure_application": {"provider": _PROVIDER}}

        with pytest.raises(
            HookError, match="is not a hook point GreetingContainer calls"
        ):
            app.build()

    def test_a_declared_point_the_container_never_calls_is_refused(self) -> None:
        with pytest.raises(HookError, match="is not a hook point it calls"):

            class TestApp(GreetingContainer):
                configure_application = declare_hook(mock_hooks.QtOnlyHook)


class TestHookResolution:
    """Tests for turning the 'hooks' configuration section into providers."""

    def test_a_declared_hook_runs_at_its_point(self) -> None:
        hook = mock_hooks.GreetingHook()

        class TestApp(GreetingContainer):
            greet = declare_hook(hook)

        TestApp().build()

        assert hook.seen == ["recorded"]

    def test_a_declared_class_is_constructed_with_its_keywords(self) -> None:
        class TestApp(GreetingContainer):
            greet = declare_hook(mock_hooks.GreetingHook, name="custom")

        TestApp().build()

        assert mock_hooks.greeted == ["custom"]

    def test_a_configured_hook_runs_at_its_point(self) -> None:
        app = GreetingContainer()
        app._config["hooks"] = {"greet": {"provider": _PROVIDER}}

        app.build()

        assert mock_hooks.greeted == ["recorded"]

    def test_kwargs_reach_the_provider_constructor(self) -> None:
        app = GreetingContainer()
        app._config["hooks"] = {
            "greet": {"provider": _PROVIDER, "kwargs": {"name": "custom"}}
        }

        app.build()

        assert mock_hooks.greeted == ["custom"]

    def test_a_subclass_keeps_the_hooks_its_base_declares(self) -> None:
        base_hook = mock_hooks.GreetingHook(name="base")
        own_hook = mock_hooks.BothPointsHook()

        class Base(GreetingContainer):
            greet = declare_hook(base_hook)

        class Derived(Base):
            farewell = declare_hook(own_hook)

        assert Derived._hook_providers == {"greet": base_hook, "farewell": own_hook}

    def test_a_subclass_replaces_a_point_its_base_declared(self) -> None:
        class Base(GreetingContainer):
            greet = declare_hook(mock_hooks.GreetingHook, name="base")

        class Derived(Base):
            greet = declare_hook(mock_hooks.GreetingHook, name="own")

        Derived().build()

        assert mock_hooks.greeted == ["own"]

    def test_a_declared_point_and_a_configured_one_run_together(self) -> None:
        leaver = mock_hooks.BothPointsHook()

        class TestApp(GreetingContainer):
            farewell = declare_hook(leaver)

        app = TestApp()
        app._config["hooks"] = {"greet": {"provider": _PROVIDER}}

        app.build()

        assert mock_hooks.greeted == ["recorded"]
        assert leaver.seen == ["farewell"]

    def test_a_point_named_twice_is_refused(self) -> None:
        class TestApp(GreetingContainer):
            greet = declare_hook(mock_hooks.GreetingHook)

        app = TestApp()
        app._config["hooks"] = {"greet": {"provider": _PROVIDER}}

        with pytest.raises(HookError, match="named both on TestApp"):
            app.build()

    def test_no_hooks_section_changes_nothing(self) -> None:
        GreetingContainer().build()

        assert mock_hooks.greeted == []

    def test_a_provider_that_does_not_serve_its_point_is_refused(self) -> None:
        app = GreetingContainer()
        app._config["hooks"] = {"greet": {"provider": "mock_pkg.hooks:NoopHook"}}

        with pytest.raises(HookError, match="does not implement Greets"):
            app.build()

    def test_a_declared_provider_that_does_not_serve_its_point_is_refused(self) -> None:
        with pytest.raises(HookError, match="does not implement Greets"):

            class TestApp(GreetingContainer):
                greet = declare_hook(mock_hooks.NoopHook)

    @pytest.mark.parametrize(
        ("provider", "expected"),
        [
            ("mock_pkg.hooks", "not a class path"),
            ("mock_pkg.nope:Hook", "cannot import"),
            ("mock_pkg.hooks:Missing", "cannot import"),
            ("mock_pkg.hooks:greeted", "is not a class"),
        ],
    )
    def test_an_unresolvable_provider_names_what_is_wrong(
        self, provider: str, expected: str
    ) -> None:
        app = GreetingContainer()
        app._config["hooks"] = {"greet": {"provider": provider}}

        with pytest.raises(HookError, match=expected):
            app.build()

    def test_a_keyword_the_provider_rejects_names_the_provider(self) -> None:
        app = GreetingContainer()
        app._config["hooks"] = {"greet": {"provider": _PROVIDER, "kwargs": {"nope": 1}}}

        with pytest.raises(HookError, match="cannot construct hook provider"):
            app.build()

    def test_a_declared_keyword_the_provider_rejects_names_the_point(self) -> None:
        with pytest.raises(HookError, match="declared at 'greet'"):

            class TestApp(GreetingContainer):
                greet = declare_hook(mock_hooks.GreetingHook, nope=1)

    def test_keywords_beside_the_provider_are_refused(self) -> None:
        app = GreetingContainer()
        app._config["hooks"] = {"greet": {"provider": _PROVIDER, "name": "custom"}}

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
        app = GreetingContainer()
        app._config["hooks"] = {"greet": entry}  # type: ignore[dict-item]

        with pytest.raises(HookError, match="'greet'"):
            app.build()

    def test_declaring_keywords_for_a_built_provider_is_refused(self) -> None:
        with pytest.raises(TypeError, match="already constructed"):
            declare_hook(mock_hooks.GreetingHook(), name="nope")  # type: ignore[call-overload]


class TestSharedProviders:
    """Tests for one provider serving more than one hook point."""

    def test_an_anchored_entry_gives_one_provider_to_both_points(self) -> None:
        app = GreetingContainer()
        app._config["hooks"] = yaml.safe_load(
            """
            greet: &shared
              provider: mock_pkg.hooks:BothPointsHook
            farewell: *shared
            """
        )

        app.build()

        hook = app._hook_by_moment["greet"]
        assert hook is app._hook_by_moment["farewell"]
        assert isinstance(hook, mock_hooks.BothPointsHook)
        assert hook.seen == ["greet", "farewell"]

    def test_a_declared_instance_serves_both_points(self) -> None:
        hook = mock_hooks.BothPointsHook()

        class TestApp(GreetingContainer):
            greet = declare_hook(hook)
            farewell = declare_hook(hook)

        TestApp().build()

        assert hook.seen == ["greet", "farewell"]

    def test_two_indistinguishable_entries_are_refused(self) -> None:
        app = GreetingContainer()
        app._config["hooks"] = {
            "greet": {"provider": "mock_pkg.hooks:BothPointsHook"},
            "farewell": {"provider": "mock_pkg.hooks:BothPointsHook"},
        }

        with pytest.raises(HookError, match="is named twice"):
            app.build()

    def test_two_entries_with_different_keywords_build_two_providers(self) -> None:
        app = GreetingContainer()
        app._config["hooks"] = {
            "greet": {
                "provider": "mock_pkg.hooks:BothPointsHook",
                "kwargs": {"name": "first"},
            },
            "farewell": {
                "provider": "mock_pkg.hooks:BothPointsHook",
                "kwargs": {"name": "second"},
            },
        }

        app.build()

        assert app._hook_by_moment["greet"] is not app._hook_by_moment["farewell"]

    def test_a_shared_provider_is_torn_down_once(self) -> None:
        hook = mock_hooks.BothPointsHook()

        class TestApp(GreetingContainer):
            greet = declare_hook(hook)
            farewell = declare_hook(hook)

        TestApp().build().shutdown()

        assert hook.teardowns == 1


class TestHooksFromAFile:
    """Tests for the 'hooks' section read from a configuration file on disk."""

    def test_a_declarative_container_reads_the_hooks_section(
        self, config_path: Path
    ) -> None:
        class TestApp(GreetingContainer, config=config_path / "mock_hooks_config.yaml"):
            pass

        TestApp().build()

        assert mock_hooks.greeted == ["custom"]

    def test_an_anchored_entry_read_from_a_file_gives_one_provider(
        self, config_path: Path
    ) -> None:
        class TestApp(
            GreetingContainer, config=config_path / "mock_shared_hook_config.yaml"
        ):
            pass

        app = TestApp().build()

        hook = app._hook_by_moment["greet"]
        assert hook is app._hook_by_moment["farewell"]
        assert isinstance(hook, mock_hooks.BothPointsHook)
        assert hook.name == "shared"
        assert hook.seen == ["greet", "farewell"]

    def test_a_shared_provider_read_from_a_file_is_torn_down_once(
        self, config_path: Path
    ) -> None:
        class TestApp(
            GreetingContainer, config=config_path / "mock_shared_hook_config.yaml"
        ):
            pass

        app = TestApp().build()
        hook = app._hook_by_moment["greet"]
        assert isinstance(hook, mock_hooks.BothPointsHook)

        app.shutdown()

        assert hook.teardowns == 1


class TestHookTeardown:
    """Tests for undoing what a hook installed."""

    def test_a_hook_is_torn_down_with_the_container(self) -> None:
        class TestApp(GreetingContainer):
            greet = declare_hook(mock_hooks.GreetingHook)

        app = TestApp().build()
        assert mock_hooks.greeted == ["recorded"]

        app.shutdown()

        assert mock_hooks.greeted == []

    def test_rebuilding_leaves_one_of_what_the_hook_installed(self) -> None:
        class TestApp(GreetingContainer):
            greet = declare_hook(mock_hooks.GreetingHook)

        app = TestApp()
        app.build()
        app.shutdown()
        app.build()

        assert mock_hooks.greeted == ["recorded"]

    def test_hooks_are_torn_down_in_reverse_order(self) -> None:
        order: list[str] = []

        class Recorder:
            def __init__(self, name: str) -> None:
                self.name = name

            def greet(self, container: AppContainer) -> None:
                pass

            def farewell(self, container: AppContainer) -> None:
                pass

            def shutdown(self) -> None:
                order.append(self.name)

        class TestApp(GreetingContainer):
            greet = declare_hook(Recorder("first"))
            farewell = declare_hook(Recorder("second"))

        TestApp().build().shutdown()

        assert order == ["second", "first"]

    def test_a_failing_teardown_does_not_block_the_next(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class TestApp(GreetingContainer):
            greet = declare_hook(mock_hooks.GreetingHook)
            farewell = declare_hook(mock_hooks.FailingShutdownHook)

        app = TestApp().build()
        with caplog.at_level(logging.ERROR, logger="redsun"):
            app.shutdown()

        assert "teardown blew up" in caplog.text
        assert mock_hooks.greeted == []

    def test_a_hook_without_a_teardown_is_skipped(self) -> None:
        class NoTeardown:
            def greet(self, container: AppContainer) -> None:
                pass

        class TestApp(GreetingContainer):
            greet = declare_hook(NoTeardown())

        TestApp().build().shutdown()


class TestBuildProgress:
    """Tests for the step names the build reports to whatever is watching."""

    def test_the_build_reports_nothing_by_default(self) -> None:
        app = AppContainer()

        app.build()

        assert app._report is not None

    def test_a_reporter_sees_every_step(self) -> None:
        seen: list[str] = []
        app = AppContainer()
        app._report = seen.append

        app.build()

        assert tuple(seen) == AppContainer.BUILD_STEPS

    def test_the_announced_steps_are_the_ones_documented(self) -> None:
        # a display sizes itself from this, so a silent reorder or rename
        # would move somebody's progress bar without failing anything
        assert AppContainer.BUILD_STEPS == (
            "virtual container",
            "devices",
            "presenters",
            "views",
            "providers",
            "wiring",
            "injection",
        )
