from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from redsun.errors import PluginError

from ._declarations import (
    Declaration,
    Declare,
    Layer,
    StackMark,
    hints,
    is_marked,
    names_of,
    refusal,
    refuse_shadowed,
    split,
)
from ._plugins import resolve

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .._config import SessionFile, StackEntry
    from ._frontend import Frontend

logger = logging.getLogger("redsun")

__all__ = ["Stack", "read_stacks", "roles_of"]


@dataclass(frozen=True)
class Stack:
    """A presenter and its views, declared as one entry."""

    cls: type
    """The class annotating the halves."""

    name: str
    """The name of the stack, which is its presenter's."""

    attribute: str
    """The attribute the session class declares the stack under."""

    presenter: str
    """The name of the presenter half."""

    views: dict[str, str]
    """The name of each view half, by role."""

    roles: dict[str, str]
    """The role of each half, by the half's name."""


def roles_of(cls: type) -> dict[str, tuple[Layer, type, dict[str, Any]]]:
    """Read the halves a stack class annotates, by role.

    Each is the half's layer, its class and the keywords its `Declare` gives.

    Raises
    ------
    TypeError
        If the class annotates anything but a presenter or a view, does not
        annotate exactly one presenter and at least one view, or has a
        constructor that needs an argument, since the session builds it with
        no arguments.
    """
    roles: dict[str, tuple[Layer, type, dict[str, Any]]] = {}
    for attr, hint in hints(cls).items():
        if attr.startswith("_"):
            continue
        target, metadata, layer = split(hint)
        if layer not in (Layer.PRESENTER, Layer.VIEW):
            raise TypeError(
                f"stack {cls.__qualname__} annotates {attr!r}, and a stack holds "
                "only presenters and views; declare it with 'AsPresenter' or "
                "'AsView'"
            )
        if not isinstance(target, type):
            raise TypeError(
                f"stack {cls.__qualname__} annotates {attr!r} as a {layer}, but "
                f"{target!r} is not a class"
            )
        declared: dict[str, Any] = {}
        for marker in metadata:
            if isinstance(marker, Declare):
                declared = marker.kwargs
        roles[attr] = (layer, target, declared)
    presenters = [
        role for role, (layer, _, _) in roles.items() if layer is Layer.PRESENTER
    ]
    if len(presenters) != 1:
        raise TypeError(
            f"stack {cls.__qualname__} annotates {len(presenters)} presenters; "
            "it needs exactly one"
        )
    if len(presenters) == len(roles):
        raise TypeError(f"stack {cls.__qualname__} annotates no view")
    required = [
        p.name
        for p in inspect.signature(cls).parameters.values()
        if p.default is p.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
    ]
    if required:
        raise TypeError(
            f"stack {cls.__qualname__} takes {', '.join(map(repr, required))} in "
            "its constructor, and the session builds it with no arguments"
        )
    return roles


def read_stacks(
    cls: type, config: SessionFile, frontend: type[Frontend]
) -> tuple[dict[str, Stack], dict[str, Declaration]]:
    """Read the stacks *cls* annotates and *config* lists.

    Returns the stacks by name, and the declarations of their halves by name.
    Keywords reach a half from the stack class, then the session file's role
    entry, then the `Declare` of the session class, the last winning. An
    entry no annotation reads is a stack too; one whose plugin does not
    resolve is logged and left out.

    Raises
    ------
    TypeError
        If a stack class breaks the rules of [`roles_of`][], a role entry or
        `Declare` names a role the stack does not have, or two halves share a
        name.
    """
    stacks: dict[str, Stack] = {}
    halves: dict[str, Declaration] = {}
    read_keys: set[str] = set()
    for attr, hint in hints(cls).items():
        if attr.startswith("_") or not is_marked(hint, StackMark):
            continue
        target, metadata, _ = split(hint)
        cfg_key, name = names_of(attr, metadata)
        inline: dict[str, Any] = {}
        for marker in metadata:
            if isinstance(marker, Declare):
                inline = marker.kwargs
        if not isinstance(target, type):
            raise TypeError(
                f"{cls.__qualname__}.{attr} is declared as a stack, but {target!r} "
                "is not a class"
            )
        read_keys.add(cfg_key)
        stacks[name] = make_stack(
            target, name, attr, config.stacks.get(cfg_key), inline, halves, frontend
        )
    for cfg_key, entry in config.stacks.items():
        if cfg_key in read_keys:
            continue
        try:
            target = resolve(entry.plugin_name, entry.plugin_id, "stacks")
        except PluginError as e:
            logger.error("Failed to load stack '%s': %s", cfg_key, e)
            continue
        if target is None:
            logger.error(
                "Stack '%s' names no plugin, and the session declares no such stack",
                cfg_key,
            )
            continue
        stacks[cfg_key] = make_stack(
            target, cfg_key, cfg_key, entry, {}, halves, frontend
        )
    refuse_shadowed(cls, stacks, "stack")
    return stacks, halves


def make_stack(
    cls: type,
    name: str,
    attribute: str,
    entry: StackEntry | None,
    inline: Mapping[str, Any],
    halves: dict[str, Declaration],
    frontend: type[Frontend],
) -> Stack:
    """Return the stack *cls* makes as *name*, and add the declarations of its halves to *halves*.

    The presenter takes *name* and each view `<name>_<role>`. *entry* gives
    the keywords of each role from a session file and *inline* those from a
    `Declare`.

    Raises
    ------
    TypeError
        If *cls* breaks the rules of [`roles_of`][], a role is not one *cls*
        has, or a half shares its name with one already in *halves*.
    """
    roles = roles_of(cls)
    given = dict(entry.model_extra or {}) if entry is not None else {}
    unknown = (given.keys() | inline.keys()) - roles.keys()
    if unknown:
        raise TypeError(
            f"stack {name!r} has no role {min(unknown)!r}; its roles: "
            f"{', '.join(map(repr, roles))}"
        )
    presenter = ""
    views: dict[str, str] = {}
    by_half: dict[str, str] = {}
    for role, (layer, half_cls, declared) in roles.items():
        half = name if layer is Layer.PRESENTER else f"{name}_{role}"
        if half in halves:
            raise TypeError(f"stack {name!r} makes {half!r}, already declared")
        halves[half] = Declaration(
            half_cls,
            half,
            layer,
            {**declared, **given.get(role, {}), **inline.get(role, {})},
            refusal=refusal(
                half_cls, layer, f"role {role!r} of stack {name!r}", frontend
            ),
            frontend=frontend,
        )
        by_half[half] = role
        if layer is Layer.PRESENTER:
            presenter = half
        else:
            views[role] = half
    return Stack(cls, name, attribute, presenter, views, by_half)
