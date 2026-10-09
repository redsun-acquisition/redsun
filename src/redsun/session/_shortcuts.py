"""How the keys components declare become the keys a window binds."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import partial
from typing import TYPE_CHECKING

from ..view._shortcut import shortcuts

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Mapping, Sequence

__all__ = ["Binding", "candidates", "holder", "resolved_shortcuts"]


@dataclass(frozen=True)
class Binding:
    """A command and the keys that run it, where they act."""

    command: str
    """The command's id: `<component>.<method>`, or an `actions` entry's id."""

    title: str
    """What the command does."""

    keys: tuple[str, ...]
    """Up to two keys; empty when the command is left unbound."""

    view: str | None
    """The view whose focus the keys need, or `None` for the whole window."""

    run: Callable[[], object] | None
    """What the keys call, or `None` for a command the frontend already holds."""

    when: Callable[[], bool] | None = None
    """While it returns false the keys do nothing; `None` for always."""


def candidates(
    components: Mapping[str, object], views: Collection[str]
) -> tuple[list[Binding], list[str]]:
    """Return the bindings *components* declare, in order, and what had to be left out.

    *views* names the components that are views; a view key on any other is
    left out and reported.
    """
    found: list[Binding] = []
    problems: list[str] = []
    for name, component in components.items():
        for method_name, (method, record) in shortcuts(component).items():
            command = f"{name}.{method_name}"
            if record.scope == "view" and name not in views:
                problems.append(
                    f"{command} asks for a key while its view has focus, but "
                    f"{name!r} is not a view; left out"
                )
                continue
            view = name if record.scope == "view" else None
            when = None if record.when is None else partial(record.when, component)
            found.append(
                Binding(command, record.title, (record.key_here(),), view, method, when)
            )
    return found, problems


def resolved_shortcuts(
    candidates: Sequence[Binding], overrides: Mapping[str, tuple[str, ...]]
) -> tuple[list[Binding], list[str]]:
    """Return *candidates* with *overrides* applied and conflicts settled, and a line per change.

    An override replaces a command's keys, an empty one unbinding it. Within
    one place, the whole window or one view, a key already taken by an
    earlier binding is removed from the later one.
    """
    known = {binding.command for binding in candidates}
    problems = [
        f"{command}: no such command; its keys are left out"
        for command in overrides
        if command not in known
    ]
    resolved: list[Binding] = []
    taken: dict[tuple[str | None, str], str] = {}
    for binding in candidates:
        keys = overrides.get(binding.command, binding.keys)
        kept = []
        for key in keys:
            owner = taken.get((binding.view, key))
            if owner is None:
                taken[(binding.view, key)] = binding.command
                kept.append(key)
                continue
            place = f" in {binding.view}" if binding.view else ""
            problems.append(
                f"{key}{place}: kept on {owner}, taken from {binding.command}"
            )
        resolved.append(replace(binding, keys=tuple(kept)))
    return resolved, problems


def holder(bindings: Sequence[Binding], binding: Binding, key: str) -> Binding | None:
    """Return the other binding holding *key* where *binding* acts, or `None`.

    Two bindings act in the same place when both act in the whole window, or
    both in one view.
    """
    return next(
        (
            other
            for other in bindings
            if other.command != binding.command
            and other.view == binding.view
            and key in other.keys
        ),
        None,
    )
