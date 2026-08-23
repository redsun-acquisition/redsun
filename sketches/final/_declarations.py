# ruff: noqa
"""Reading component declarations off a container class."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    NewType,
    get_args,
    get_origin,
    get_type_hints,
)

from ophyd_async.core import Device
from typing_extensions import TypeForm

from redsun.presenter import PPresenter
from redsun.view import PView

from ._scopes import AppScope

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class Declare:
    """Inline keyword arguments, overriding anything the config supplies."""

    kwargs: dict[str, Any] = field(default_factory=dict)

    def __init__(self, **kwargs: Any) -> None:
        object.__setattr__(self, "kwargs", kwargs)


@dataclass(frozen=True)
class FromConfig:
    """Config key, for keys that are not identifiers or must differ."""

    key: str


@dataclass(frozen=True)
class Alias:
    """Component name, when it must differ from the attribute name."""

    name: str


MARKERS = (Declare, FromConfig, Alias)

SECTIONS = {"device": "devices", "presenter": "presenters", "view": "views"}


class Declaration:
    """One component: its class, its name, its config, its dishka key."""

    __slots__ = ("cfg_kwargs", "cls", "instance", "key", "kind", "name", "scope")

    def __init__(
        self, cls: type, name: str, kind: str, cfg_kwargs: dict[str, Any]
    ) -> None:
        self.cls = cls
        self.name = name
        self.kind = kind
        self.cfg_kwargs = cfg_kwargs
        self.key = NewType(name, cls)
        self.scope: AppScope = AppScope.COMPONENT
        self.instance: Any = None

    def __repr__(self) -> str:
        state = "built" if self.instance is not None else "pending"
        return f"Declaration({self.name!r}, {self.kind}, {state})"


def kind_of(cls: TypeForm[Any] | object) -> str | None:
    """Device, presenter or view, or None if *cls* is not a component.

    Runs on the class named by the annotation, so it is a genuine class-level
    gate: a class that cannot be built is rejected before anything is built.
    """
    if not isinstance(cls, type):
        return None
    if issubclass(cls, Device):
        return "device"
    if not _leads_with_name(cls):
        return None
    return "view" if issubclass(cls, PView) else "presenter"


def _leads_with_name(cls: type) -> bool:
    """The only positional contract left: ``(name, /)``."""
    try:
        params = list(inspect.signature(cls).parameters.values())
    except (TypeError, ValueError):
        return False
    return bool(params) and params[0].name == "name"


def read(cls: type, config: Mapping[str, Any]) -> dict[str, Declaration]:
    """Collect the declarations of *cls*, at build time.

    Annotations rather than assigned values, so no descriptor is installed and
    no class attribute is mutated. ``get_type_hints`` walks the MRO, so
    inheritance needs no merge step of its own.

    A component named in *config* but never annotated is still declared; the
    annotation only adds a typed attribute to reach it by.
    """
    declarations: dict[str, Declaration] = {}

    for attr, hint in get_type_hints(cls, include_extras=True).items():
        if attr.startswith("_"):
            continue
        target, metadata = _split(hint)
        kind = kind_of(target)
        if kind is None:
            continue

        inline: dict[str, Any] = {}
        cfg_key = attr
        name = attr
        for marker in metadata:
            if isinstance(marker, Declare):
                inline = marker.kwargs
            elif isinstance(marker, FromConfig):
                cfg_key = marker.key
            elif isinstance(marker, Alias):
                name = marker.name

        section = config.get(SECTIONS[kind], {})
        declarations[name] = Declaration(
            target, name, kind, {**_entry(section, cfg_key), **inline}
        )

    for kind, section_name in SECTIONS.items():
        for cfg_key, entry in config.get(section_name, {}).items():
            if cfg_key in declarations or not isinstance(entry, dict):
                continue
            target = _from_manifest(entry, kind)
            if target is not None:
                declarations[cfg_key] = Declaration(
                    target, cfg_key, kind, _strip_meta(entry)
                )

    return declarations


def _split(hint: Any) -> tuple[Any, tuple[Any, ...]]:
    """``Annotated[X, ...]`` into ``(X, metadata)``; a bare hint into ``(X, ())``."""
    if get_origin(hint) is Annotated:
        target, *metadata = get_args(hint)
        return target, tuple(metadata)
    return hint, ()


def _entry(section: Mapping[str, Any], key: str) -> dict[str, Any]:
    entry = section.get(key) or {}
    return _strip_meta(entry) if isinstance(entry, dict) else {}


def _strip_meta(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if k not in ("plugin_name", "plugin_id")}


def _from_manifest(entry: Mapping[str, Any], kind: str) -> type | None:
    """Import the class a config entry names, via the plugin manifest."""
    ...


__all__ = ["Alias", "Declaration", "Declare", "FromConfig", "kind_of", "read"]
