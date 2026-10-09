"""Tests for declaring a keyboard shortcut on a component's method."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from redsun import Shortcut, shortcut, slot
from redsun.ports import ports
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
