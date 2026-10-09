"""Tests for declaring a keyboard shortcut on a component's method."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, cast

import pytest

from redsun import Shortcut, shortcut, slot
from redsun.ports import ports
from redsun.session._shortcuts import Binding, candidates, holder, resolved_shortcuts
from redsun.view._shortcut import shortcuts

if TYPE_CHECKING:
    from collections.abc import Callable


class Base:
    def __init__(self) -> None:
        self.ran: list[str] = []

    @shortcut("Ctrl+R", title="Run")
    def run(self) -> None:
        self.ran.append("run")


class Child(Base):
    @shortcut("Escape", title="Stop", scope="view")
    def stop(self) -> None:
        self.ran.append("stop")

    def plain(self) -> None:
        self.ran.append("plain")


class Panel:
    @shortcut("Ctrl+R", title="Run")
    def run(self) -> None: ...

    @shortcut("Escape", title="Cancel", scope="view")
    def cancel(self) -> None: ...


class Gated:
    def __init__(self) -> None:
        self.ready = False

    def _is_ready(self) -> bool:
        return self.ready

    @shortcut("Left", title="Back", scope="view", when=_is_ready)
    def back(self) -> None: ...


class Controller:
    @shortcut("Ctrl+R", title="Restart")
    def restart(self) -> None: ...

    @shortcut("F5", title="Refresh", scope="view")
    def refresh(self) -> None: ...


def binding(command: str, *keys: str, view: str | None = None) -> Binding:
    """Return a binding with no method, for resolution alone."""
    return Binding(command, command, keys, view, None)


def test_a_component_lists_its_shortcuts_base_first() -> None:
    """List each decorated method, a base class's first, bound to the component."""
    child = Child()

    found = shortcuts(child)

    assert list(found) == ["run", "stop"]
    method, record = found["stop"]
    method()
    assert child.ran == ["stop"]
    assert record == Shortcut("Escape", "Stop", scope="view")


def test_a_platform_key_wins_on_its_platform() -> None:
    """Give the platform's own key where one is set, and the key otherwise."""
    record = Shortcut("Ctrl+K", "Clear", mac="Meta+K", win="Alt+K", linux="Ctrl+L")
    expected = {"darwin": "Meta+K", "win32": "Alt+K"}.get(sys.platform, "Ctrl+L")

    assert record.key_here() == expected
    assert Shortcut("Ctrl+K", "Clear").key_here() == "Ctrl+K"


@pytest.mark.parametrize(
    ("make", "problem"),
    [
        (lambda: shortcut("Ctrl+R", title="Run", scope="dock"), "scope"),  # type: ignore[arg-type]
        (lambda: shortcut("", title="Run"), "key"),
        (lambda: shortcut("Ctrl+R", title=""), "title"),
    ],
)
def test_a_shortcut_refuses_what_it_cannot_record(
    make: Callable[[], object], problem: str
) -> None:
    """Refuse an unknown scope, an empty key and an empty title."""
    with pytest.raises(ValueError, match=problem):
        make()


def test_a_method_that_needs_arguments_is_refused() -> None:
    """Refuse a method a key could not call, naming it."""
    with pytest.raises(TypeError, match="needs"):

        class Wrong:
            @shortcut("Ctrl+R", title="Run")
            def run(self, plan: str) -> None: ...


def test_a_coroutine_method_is_refused_for_now() -> None:
    """Refuse an async method, which a key would call without running."""
    with pytest.raises(TypeError, match="coroutine"):

        class Wrong:
            @shortcut("Ctrl+R", title="Run")
            async def run(self) -> None: ...


def test_a_slot_can_also_be_a_shortcut() -> None:
    """Keep both records when slot and shortcut decorate one method, in either order."""

    class Both:
        @slot
        @shortcut("Escape", title="Stop")
        def stop(self) -> None: ...

        @shortcut("F5", title="Refresh")
        @slot
        def refresh(self) -> None: ...

    both = Both()

    assert list(shortcuts(both)) == ["stop", "refresh"]
    assert {"stop", "refresh"} <= set(ports(both).slots)


def test_components_become_bindings_in_declaration_order() -> None:
    """Name each binding after its component and method, a view key with its view."""
    found, problems = candidates(
        {"panel": Panel(), "controller": Controller()}, views={"panel"}
    )

    assert [(b.command, b.keys, b.view) for b in found] == [
        ("panel.run", ("Ctrl+R",), None),
        ("panel.cancel", ("Escape",), "panel"),
        ("controller.restart", ("Ctrl+R",), None),
    ]
    assert problems == [
        (
            "controller.refresh asks for a key while its view has focus, but "
            "'controller' is not a view; left out"
        )
    ]


def test_the_first_window_key_wins_and_both_are_named() -> None:
    """Keep a window key on the first command asking for it, and name both in the report."""
    resolved, problems, _ = resolved_shortcuts(
        [binding("panel.run", "Ctrl+R"), binding("controller.restart", "Ctrl+R")], {}
    )

    assert [(b.command, b.keys) for b in resolved] == [
        ("panel.run", ("Ctrl+R",)),
        ("controller.restart", ()),
    ]
    assert problems == ["Ctrl+R: kept on panel.run, taken from controller.restart"]


def test_a_view_key_shadowing_a_window_key_is_kept_without_report() -> None:
    """Keep a view key on the same combination as a window key, and report nothing."""
    resolved, problems, _ = resolved_shortcuts(
        [
            binding("panel.run", "Ctrl+R"),
            binding("panel.again", "Ctrl+R", view="panel"),
        ],
        {},
    )

    assert [b.keys for b in resolved] == [("Ctrl+R",), ("Ctrl+R",)]
    assert problems == []


def test_two_keys_of_one_view_conflict() -> None:
    """Treat two keys of one view on one combination as a conflict."""
    resolved, problems, _ = resolved_shortcuts(
        [
            binding("panel.a", "F5", view="panel"),
            binding("panel.b", "F5", view="panel"),
        ],
        {},
    )

    assert [b.keys for b in resolved] == [("F5",), ()]
    assert problems == ["F5 in panel: kept on panel.a, taken from panel.b"]


def test_overrides_replace_drop_and_report_unknown_commands() -> None:
    """Replace a command's keys, drop one given no key, and name an override for no command."""
    resolved, problems, _ = resolved_shortcuts(
        [binding("panel.run", "Ctrl+R"), binding("panel.stop", "Escape")],
        {"panel.run": ("Ctrl+Shift+R", "F9"), "panel.stop": (), "ghost.run": ("F1",)},
    )

    assert [(b.command, b.keys) for b in resolved] == [
        ("panel.run", ("Ctrl+Shift+R", "F9")),
        ("panel.stop", ()),
    ]
    assert problems == ["ghost.run: no such command; its keys are left out"]


def test_a_second_shortcut_on_one_method_is_refused() -> None:
    """Refuse a second key on one method, which would drop the first."""
    with pytest.raises(TypeError, match="already"):

        class Twice:
            @shortcut("F1", title="One")
            @shortcut("F2", title="Two")
            def run(self) -> None: ...


def test_a_condition_is_asked_of_its_component() -> None:
    """Call a binding's condition with the component that declared it."""
    gated = Gated()
    (binding,), _ = candidates({"gated": gated}, {"gated"})
    assert binding.when is not None

    before = binding.when()
    gated.ready = True

    assert (before, binding.when()) == (False, True)


def test_a_condition_that_cannot_be_called_is_refused() -> None:
    """Refuse a condition that is not a function."""
    with pytest.raises(ValueError, match="condition"):
        shortcut("Left", title="Back", when=cast("Any", "ready"))


def test_the_holder_of_a_key_is_another_command_in_the_same_place() -> None:
    """Find the other command holding a key where a binding acts, and none elsewhere."""
    run = Binding("panel.run", "Run", ("Ctrl+R",), None, None)
    restart = Binding("controller.restart", "Restart", ("F5",), None, None)
    refresh = Binding("panel.refresh", "Refresh", ("F5",), "panel", None)

    found = [
        holder([run, restart, refresh], run, "F5"),
        holder([run, restart, refresh], refresh, "F5"),
        holder([run, restart, refresh], run, "Ctrl+R"),
    ]

    assert found == [restart, None, None]


def test_a_saved_key_wins_over_an_earlier_default_and_is_only_noted() -> None:
    """Settle saved commands first, so a saved key beats an earlier default, and note that conflict apart."""
    resolved, problems, notes = resolved_shortcuts(
        [
            binding("panel.run", "Ctrl+R"),
            binding("controller.restart", "Ctrl+R"),
            binding("panel.walk", "F1"),
        ],
        {"panel.run": (), "panel.walk": ("Ctrl+R",)},
        saved={"panel.run", "panel.walk"},
    )

    assert [(b.command, b.keys) for b in resolved] == [
        ("panel.run", ()),
        ("controller.restart", ()),
        ("panel.walk", ("Ctrl+R",)),
    ]
    assert problems == []
    assert notes == ["Ctrl+R: kept on panel.walk, taken from controller.restart"]
