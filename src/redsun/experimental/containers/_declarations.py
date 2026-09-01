from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Final,
    NewType,
    TypeAlias,
    get_args,
    get_origin,
    get_type_hints,
)

from ophyd_async.core import Device

from redsun._hooks import HookError, known_points
from redsun.experimental.containers._frontend import Frontend
from redsun.experimental.containers._plugins import META_KEYS, resolve
from redsun.experimental.view._placement import Placement

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

logger = logging.getLogger("redsun")

__all__ = [
    "Alias",
    "Declaration",
    "Declare",
    "FromConfig",
    "Hook",
    "HookDeclaration",
    "Key",
    "Layer",
    "Serves",
    "check",
    "read",
    "read_hooks",
]

Key: TypeAlias = Any
"""A dependency key.

Not ``TypeForm``: a `NewType` built at runtime is a type expression only at
runtime, and no type checker can model one. Hints read from an annotation stay
``TypeForm[Any]``; keys the container synthesises are this.
"""


class Layer(StrEnum):
    """The layer a declared component belongs to.

    Carried as the metadata of a declaration's annotation. `redsun.experimental.containers.components`
    spells the three out. A member is its own name in a message, so it needs no
    ``.value``.
    """

    DEVICE = "device"
    PRESENTER = "presenter"
    VIEW = "view"


SECTIONS = {
    Layer.DEVICE: "devices",
    Layer.PRESENTER: "presenters",
    Layer.VIEW: "views",
}


@dataclass(frozen=True)
class Declare:
    """Inline keyword arguments, overriding anything the configuration gives."""

    kwargs: dict[str, Any] = field(default_factory=dict)

    def __init__(self, **kwargs: Any) -> None:
        object.__setattr__(self, "kwargs", kwargs)


@dataclass(frozen=True)
class FromConfig:
    """Configuration key, when it cannot be the attribute name.

    Needed only for keys that are not identifiers, or that deliberately
    differ from the attribute they are read into.
    """

    key: str


@dataclass(frozen=True)
class Alias:
    """Component name, when it must differ from the attribute name."""

    name: str


@dataclass(frozen=True)
class Hook:
    """Marks an annotation as a hook rather than a component.

    Carried by `redsun.experimental.AsHook`. A hook is a callback at a fixed
    point in the toolkit's startup sequence; it is built and called, never
    injected, and it is not a layer.
    """


@dataclass(frozen=True)
class Serves:
    """The hook points one provider serves, when the attribute name is not one.

    Declaring several is how one provider instance serves several points: the
    annotation names the class once, so one object is built for them all.
    """

    moments: tuple[str, ...]

    def __init__(self, *moments: str) -> None:
        object.__setattr__(self, "moments", tuple(moments))


@dataclass(frozen=True)
class HookDeclaration:
    """A declared hook provider, and the points it was declared to serve."""

    cls: type
    moments: tuple[str, ...]
    kwargs: dict[str, Any]


_MARKERS = (Declare, FromConfig, Alias, Serves)


class Declaration:
    """A declared component, before and after it is built.

    ``key`` is a distinct type per component name, so two instances of one
    class stay separable in a type-keyed graph.
    """

    __slots__ = ("cfg_kwargs", "cls", "instance", "key", "kind", "name")

    def __init__(
        self, cls: type, name: str, kind: Layer, cfg_kwargs: dict[str, Any]
    ) -> None:
        self.cls = cls
        self.name = name
        self.kind = kind
        self.cfg_kwargs = cfg_kwargs
        self.key: Key = NewType(name, cls)
        self.instance: Any = None

    def __repr__(self) -> str:
        state = "built" if self.instance is not None else "pending"
        return f"Declaration({self.name!r}, {self.kind}, {state})"


def check(
    target: object, layer: Layer, where: str, frontend: type[Frontend] = Frontend
) -> type:
    """Confirm *target* may be declared in *layer*, and return it.

    A view is a class declaring a ``placement``; a presenter is one that does
    not. When the placement is a value on the class it is checked against the
    frontend here, and when it is a property only the built instance can
    answer, so `redsun.experimental.AppContainer` asks again then.

    Raises
    ------
    TypeError
        If *target* is not a class, does not belong to the layer it is
        declared in, or asks for a placement the frontend does not attach.
    """
    if not isinstance(target, type):
        raise TypeError(
            f"{where} is declared as a {layer}, but {target!r} is not a class"
        )
    if layer is Layer.DEVICE:
        if not issubclass(target, Device):
            raise TypeError(
                f"{where} is declared as a device, but {target.__name__} does not "
                "subclass 'ophyd_async.core.Device'"
            )
        return target
    if issubclass(target, Device):
        raise TypeError(
            f"{where} is declared as a {layer}, but {target.__name__} is an "
            "'ophyd_async.core.Device'; declare it with 'AsDevice'"
        )
    if not leads_with_name(target):
        raise TypeError(
            f"{where} is declared as a {layer}, but {target.__name__} does "
            "not take 'name' as its first parameter"
        )
    declared = inspect.getattr_static(target, "placement", None)
    if layer is not Layer.VIEW:
        if declared is not None:
            raise TypeError(
                f"{where} is declared as a {layer}, but {target.__name__} "
                "declares a 'placement'; declare it with 'AsView'"
            )
        return target
    if declared is None:
        raise TypeError(
            f"{where} is declared as a view, but {target.__name__} declares no "
            "'placement'. A view says where it attaches; a component that "
            "attaches nowhere is a presenter."
        )
    if isinstance(declared, Placement):
        frontend.check_placement(target, declared, where)
    return target


NAME_KINDS: Final = frozenset(
    {
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    }
)
"""The parameter kinds the framework can pass a component's name as."""


def leads_with_name(cls: type) -> bool:
    """Whether the framework can hand *cls* its name.

    True when the first parameter is called ``name`` and is of a kind that can
    be passed one value. A variadic first parameter is refused: a name arriving
    inside ``*args`` or ``**kwargs`` is not a name the component can be built
    with.
    """
    first = _first_parameter(cls)
    return first is not None and first.name == "name" and first.kind in NAME_KINDS


def takes_name_by_keyword(cls: type) -> bool:
    """Whether *cls* wants its name as a keyword rather than positionally."""
    first = _first_parameter(cls)
    return first is not None and first.kind is inspect.Parameter.KEYWORD_ONLY


def _first_parameter(cls: type) -> inspect.Parameter | None:
    try:
        params = list(inspect.signature(cls).parameters.values())
    except (TypeError, ValueError):
        return None
    return params[0] if params else None


def read(
    cls: type, config: Mapping[str, Any], frontend: type[Frontend] = Frontend
) -> dict[str, Declaration]:
    """Collect the component declarations of *cls*.

    Declarations are annotations, so nothing is collected at class creation
    and no attribute is replaced by a descriptor. ``get_type_hints`` walks the
    MRO, so inheritance needs no merge of its own.

    An annotation is a declaration only if it carries a layer, which is what
    `redsun.experimental.containers.components` adds; anything else is an ordinary attribute.

    A component named in *config* but never annotated is declared too, its
    layer coming from the section it appears under; an annotation only adds a
    typed attribute to reach it by.

    Raises
    ------
    TypeError
        If a declared class does not belong to the layer it is declared in.
    """
    declarations: dict[str, Declaration] = {}

    for attr, hint in _hints(cls).items():
        if attr.startswith("_") or _is_hook(hint):
            continue
        target, metadata, kind = _split(hint)
        if kind is None:
            _warn_if_forgotten(cls, attr, target)
            continue
        check(target, kind, f"{cls.__qualname__}.{attr}", frontend)

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

    declarations.update(_from_config(config, declarations.keys(), frontend))
    _refuse_shadowed(cls, declarations)
    return declarations


def read_hooks(cls: type, points: Mapping[str, type]) -> dict[str, HookDeclaration]:
    """Collect the hook declarations of *cls*, by the point each serves.

    The attribute name is the point; a `Serves` marker names them instead, and
    naming several is how one provider instance serves several. `Declare`
    carries the provider's constructor arguments.

    Raises
    ------
    HookError
        If a declaration is not a class, names a point *cls* does not call, or
        two declarations claim one point.
    """
    found: dict[str, HookDeclaration] = {}
    for attr, hint in _hints(cls).items():
        if attr.startswith("_") or not _is_hook(hint):
            continue
        target, metadata, _ = _split(hint)
        where = f"{cls.__qualname__}.{attr}"
        if not isinstance(target, type):
            raise HookError(
                f"{where} is declared as a hook, but {target!r} is not a class"
            )
        served: tuple[str, ...] = (attr,)
        kwargs: dict[str, Any] = {}
        for marker in metadata:
            if isinstance(marker, Serves):
                served = marker.moments
            elif isinstance(marker, Declare):
                kwargs = marker.kwargs
        declaration = HookDeclaration(target, served, kwargs)
        for moment in served:
            if moment not in points:
                raise HookError(
                    f"{where} declares a hook at {moment!r}, which is not a "
                    f"hook point {cls.__name__} calls; {known_points(points)}"
                )
            claimed = found.get(moment)
            if claimed is not None:
                raise HookError(
                    f"{where} and {claimed.cls.__name__} both claim the hook "
                    f"point {moment!r}; a hook point takes one provider"
                )
            found[moment] = declaration
    return found


def _refuse_shadowed(cls: type, declarations: Mapping[str, Declaration]) -> None:
    """Refuse a component whose name the container already answers itself.

    A built component is read through ``__getattr__``, which only runs when
    ordinary lookup fails, so a component sharing a name with a method or a
    property of the container could never be reached.
    """
    for name in declarations:
        if not hasattr(cls, name):
            continue
        raise TypeError(
            f"{cls.__qualname__} declares a component named {name!r}, but that "
            f"is already an attribute of the container, so reading it would "
            "give the attribute rather than the component. Rename it, or name "
            "the component something else with Alias."
        )


def _warn_if_forgotten(cls: type, attr: str, target: object) -> None:
    """Point out an annotation that looks like a component but declares no layer.

    Without a layer the annotation is an ordinary attribute, which is the right
    answer for a plain one and a silent omission for a component.
    """
    if not isinstance(target, type):
        return
    if not issubclass(target, Device) and not leads_with_name(target):
        return
    logger.warning(
        "%s.%s annotates %s but declares no layer, so it is an ordinary "
        "attribute and no component is built. Wrap it in AsDevice, AsPresenter "
        "or AsView if it was meant to be one.",
        cls.__qualname__,
        attr,
        target.__name__,
    )


def _from_config(
    config: Mapping[str, Any], declared: Iterable[str], frontend: type[Frontend]
) -> dict[str, Declaration]:
    """Collect the components named only in *config*.

    A configuration entry carrying ``plugin_name`` and ``plugin_id`` is a
    component even when the container class never annotates it; the annotation
    only adds a typed attribute to reach it by. An entry already declared is
    left alone, so a class-body declaration wins.

    The section an entry appears under is its layer, so nothing here has to be
    marked; it is checked against that layer all the same.
    """
    found: dict[str, Declaration] = {}
    for kind, section_name in SECTIONS.items():
        for cfg_key, entry in config.get(section_name, {}).items():
            if cfg_key in declared or not isinstance(entry, dict):
                continue
            target = resolve(entry, section_name)
            if target is None:
                continue
            check(
                target, kind, f"configuration entry {section_name}.{cfg_key}", frontend
            )
            found[cfg_key] = Declaration(target, cfg_key, kind, _strip(entry))
    return found


def _strip(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if k not in META_KEYS}


def _hints(cls: type) -> dict[str, Any]:
    """Resolve the annotations of *cls* and its bases, one class at a time.

    ``from __future__ import annotations`` makes every annotation a string,
    resolved against the defining module's globals. Resolving the whole MRO in
    one call fails entirely if any single class references a name that is only
    imported under ``TYPE_CHECKING``, so each is resolved on its own and the
    one at fault is named.

    Raises
    ------
    NameError
        If a class declares an annotation that cannot be resolved at runtime.
    """
    resolved: dict[str, Any] = {}
    for klass in reversed(cls.__mro__):
        if not getattr(klass, "__annotations__", None):
            continue
        try:
            resolved.update(get_type_hints(klass, include_extras=True))
        except NameError as e:
            if e.name in globals():
                raise
            raise NameError(
                f"cannot resolve the annotations of {klass.__qualname__}: "
                f"{e.name!r} is not available at runtime. A class holding "
                "component declarations must import the names it annotates "
                "outside 'if TYPE_CHECKING'."
            ) from e
    return resolved


def _split(hint: Any) -> tuple[Any, tuple[Any, ...], Layer | None]:
    """Separate a declaration's type, its option markers, and its layer."""
    if get_origin(hint) is not Annotated:
        return hint, (), None
    target, *metadata = get_args(hint)
    layers = [m for m in metadata if isinstance(m, Layer)]
    markers = tuple(m for m in metadata if isinstance(m, _MARKERS))
    return target, markers, layers[0] if layers else None


def _is_hook(hint: Any) -> bool:
    if get_origin(hint) is not Annotated:
        return False
    return any(isinstance(m, Hook) for m in get_args(hint)[1:])


def _entry(section: Mapping[str, Any], key: str) -> dict[str, Any]:
    entry = section.get(key) or {}
    if not isinstance(entry, dict):
        return {}
    return {k: v for k, v in entry.items() if k not in META_KEYS}
