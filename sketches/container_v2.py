# ruff: noqa
"""The container layer redesigned around Annotated, going further than option 1.

Supersedes `container_layer.py`. Five things change beyond swapping the DI
backend, each of which removes machinery rather than adding it:

  1. __init_subclass__ disappears. Declarations are read once, at build, from
     get_type_hints(type(self), include_extras=True). Nothing is collected at
     class-creation time and no class attribute is ever mutated.
  2. `config` is a ClassVar, not an __init_subclass__ keyword. It follows normal
     MRO rules, is typed, and accepts a mapping so tests need no file.
  3. One declaration concept. The kind (device / presenter / view) follows from
     the annotated class, so the three _*Field and three _*Component classes
     collapse to one _Declaration.
  4. The attribute name is the config key by default. `FromConfig` survives only
     for the case where they genuinely differ.
  5. The declarative path and the from_config path stop being two code paths.
     A component in the YAML that has no annotation is still built; an
     annotation just adds typed access.

Not executed: dishka is not installed here.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from pathlib import Path
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Annotated as A,
    Any,
    ClassVar,
    Generic,
    NewType,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from dishka import Provider, Scope, make_container

from redsun.presenter import PPresenter
from redsun.view import PView
from redsun.virtual import VirtualContainer

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dishka import Container
    from ophyd_async.core import Device, DeviceMap

logger = logging.getLogger("redsun")

D = TypeVar("D")


# ==========================================================================
# Declaration metadata
# ==========================================================================


@dataclass(frozen=True)
class Declare:
    """Inline keyword arguments, merged under anything the config supplies."""

    kwargs: dict[str, Any] = field(default_factory=dict)

    def __init__(self, **kwargs: Any) -> None:
        object.__setattr__(self, "kwargs", kwargs)


@dataclass(frozen=True)
class FromConfig:
    """Config key, when it cannot be the attribute name.

    Only needed for keys that are not identifiers ("xy-motor") or that
    deliberately differ from the attribute.
    """

    key: str


@dataclass(frozen=True)
class Alias:
    """Component name, when it must differ from the attribute name."""

    name: str


_MARKERS = (Declare, FromConfig, Alias)


# ==========================================================================
# Declarations
# ==========================================================================


class _Declaration:
    """One component: where it comes from, what it is called, how it is keyed."""

    __slots__ = ("cfg_kwargs", "cls", "instance", "key", "kind", "name")

    def __init__(self, cls: type, name: str, kind: str, cfg_kwargs: dict[str, Any]):
        self.cls = cls
        self.name = name
        self.kind = kind
        self.cfg_kwargs = cfg_kwargs
        self.key = NewType(name, cls)
        self.instance: Any = None


def _kind_of(cls: type) -> str:
    """Device, presenter or view, from the class alone.

    This is the class-level half of the dual gate, and unlike the positional
    inspection it currently rests on, it runs on a real class object taken
    from the annotation.
    """
    from ophyd_async.core import Device as _Device

    if isinstance(cls, type) and issubclass(cls, _Device):
        return "device"
    if _expects_name(cls) and issubclass(cls, PView):  # structural, not nominal
        return "view"
    if _expects_name(cls):
        return "presenter"
    raise TypeError(f"{cls!r} is not a device, a presenter or a view")


def _expects_name(cls: type) -> bool:
    """The one positional contract that survives: (name, /)."""
    try:
        params = list(inspect.signature(cls).parameters.values())
    except (TypeError, ValueError):
        return False
    return bool(params) and params[0].name == "name"


def _declarations(cls: type, config: Mapping[str, Any]) -> dict[str, _Declaration]:
    """Read every declaration off the class, at build time.

    Annotations, not assigned values, so nothing has to be collected in
    __init_subclass__ and no descriptor is installed. Inheritance is handled by
    get_type_hints walking the MRO, which is one fewer loop than merging
    per-base ClassVar dicts.
    """
    hints = get_type_hints(cls, include_extras=True)
    sections = {"device": "devices", "presenter": "presenters", "view": "views"}
    out: dict[str, _Declaration] = {}

    for attr, hint in hints.items():
        if attr.startswith("_") or get_origin(hint) is not A:
            continue
        target, *metadata = get_args(hint)
        if not any(isinstance(m, _MARKERS) for m in metadata):
            continue

        inline = next((m.kwargs for m in metadata if isinstance(m, Declare)), {})
        cfg_key = next((m.key for m in metadata if isinstance(m, FromConfig)), attr)
        name = next((m.name for m in metadata if isinstance(m, Alias)), attr)

        kind = _kind_of(target)
        section = config.get(sections[kind], {})
        out[name] = _Declaration(
            target, name, kind, {**section.get(cfg_key, {}), **inline}
        )

    # a component present in the config but never annotated is still built;
    # it simply has no typed attribute to reach it by
    for kind, section_name in sections.items():
        for cfg_key, entry in config.get(section_name, {}).items():
            if cfg_key in out or not isinstance(entry, dict):
                continue
            target = _resolve_from_manifest(entry, kind)
            if target is not None:
                out[cfg_key] = _Declaration(target, cfg_key, kind, _strip_meta(entry))
    return out


def _resolve_from_manifest(entry: dict[str, Any], kind: str) -> type | None: ...
def _strip_meta(entry: dict[str, Any]) -> dict[str, Any]: ...


# ==========================================================================
# Factory generation
# ==========================================================================


def _optional_arg(hint: Any) -> Any | None:
    """Return X for `X | None`, preserving any Annotated metadata on X."""
    if get_origin(hint) not in (Union, UnionType):
        return None
    args = [a for a in get_args(hint) if a is not type(None)]
    return args[0] if len(args) == 1 else None


def _injectable(cls: type, cfg_kwargs: dict[str, Any]) -> dict[str, Any]:
    """Constructor parameters the graph must fill.

    include_extras is load-bearing: dishka's own markers (FromComponent) live
    in the same Annotated metadata slot and must survive the copy.
    """
    hints = get_type_hints(cls.__init__, include_extras=True)
    out: dict[str, Any] = {}
    for pname, param in inspect.signature(cls).parameters.items():
        if pname in ("self", "name") or pname in cfg_kwargs:
            continue
        if param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
            continue
        if pname not in hints:
            raise TypeError(f"{cls.__name__}.{pname} has no annotation")
        out[pname] = hints[pname]
    return out


def _factory(decl: _Declaration, available: frozenset[Any]) -> Any:
    """The callable dishka inspects and calls.

    Optional parameters are decided here, statically: if nothing in the
    assembled providers offers the type, None is closed over and the parameter
    never reaches dishka. That is the whole of what try_require used to do.
    """
    required: dict[str, Any] = {}
    absent: dict[str, None] = {}
    for pname, hint in _injectable(decl.cls, decl.cfg_kwargs).items():
        inner = _optional_arg(hint)
        if inner is None:
            required[pname] = hint
        elif inner in available:
            required[pname] = inner
        else:
            absent[pname] = None

    def build(**deps: Any) -> Any:
        return decl.cls(decl.name, **decl.cfg_kwargs, **absent, **deps)

    build.__name__ = f"build_{decl.name}"
    build.__annotations__ = {**required, "return": decl.key}
    return build


def _provided_keys(providers: list[Provider]) -> frozenset[Any]: ...


# ==========================================================================
# The container
# ==========================================================================


class Frontend: ...


class Qt(Frontend): ...


FE = TypeVar("FE", bound=Frontend)


class AppContainer(Generic[FE]):
    """No metaclass, no __init_subclass__, no descriptors, no class mutation.

    Everything happens in build(), which can therefore be read top to bottom.
    """

    config: ClassVar[str | Path | Mapping[str, Any] | None] = None
    providers: ClassVar[list[Provider]] = []

    def __init__(self) -> None:
        self._bus = VirtualContainer()
        self._di: Container | None = None
        self._declarations: dict[str, _Declaration] = {}
        self._devices: dict[str, Device] = {}
        self._is_built = False

    def __getattr__(self, name: str) -> Any:
        """Reach a declared component. mypy uses the annotation, not this."""
        try:
            return self._declarations[name].instance
        except KeyError:
            raise AttributeError(name) from None

    def build(self) -> AppContainer[FE]:
        """Three phases. Each ordering has a one-sentence reason.

        1. Devices, built here rather than by dishka because a device that
           fails to build is logged and skipped, and a graph edge cannot be.
        2. Components, resolved by dishka in dependency order.
        3. Wiring, which needs every instance to exist.
        """
        cfg = _read_config(self.config)
        self._bus._set_configuration(cfg)
        self._declarations = _declarations(type(self), cfg)

        self._devices = self._build_devices()

        framework = Provider(scope=Scope.APP)
        framework.provide(lambda: self._bus, provides=VirtualContainer)
        framework.provide(lambda: DeviceMap(self._devices), provides=DeviceMap)

        providers = [framework, *self.providers, *_plugin_providers(cfg)]
        available = _provided_keys(providers)

        components = Provider(scope=Scope.APP)
        for decl in self._declarations.values():
            if decl.kind == "device":
                continue
            components.provide(_factory(decl, available), provides=decl.key)
        self._alias_unique_classes(components)

        self._di = make_container(components, *providers)

        for decl in self._declarations.values():
            if decl.kind == "device":
                continue
            decl.instance = self._di.get(decl.key)
            self._validate(decl)
            self._bus.register_signals(decl.instance, name=decl.name)

        self._bus._set_components(
            {d.name: d.instance for d in self._declarations.values() if d.instance}
        )
        self.wire()
        self._apply_wiring_config(cfg)
        self._is_built = True
        return self

    def _alias_unique_classes(self, provider: Provider) -> None:
        """A class declared exactly once can also be injected by its type."""
        by_class: dict[type, list[_Declaration]] = {}
        for decl in self._declarations.values():
            by_class.setdefault(decl.cls, []).append(decl)
        for cls, decls in by_class.items():
            if len(decls) == 1:
                provider.alias(source=decls[0].key, provides=cls)

    def _validate(self, decl: _Declaration) -> None:
        protocol = PPresenter if decl.kind == "presenter" else PView
        if not isinstance(decl.instance, protocol):
            raise TypeError(
                f"{type(decl.instance).__name__!r} ({decl.kind} {decl.name!r}) "
                f"does not implement {protocol.__name__}"
            )

    def _build_devices(self) -> dict[str, Device]: ...
    def _apply_wiring_config(self, cfg: Mapping[str, Any]) -> None: ...
    def wire(self) -> None: ...


def _read_config(source: Any) -> Mapping[str, Any]:
    """A path, or a mapping straight from a test. Read once, at build."""
    ...


def _plugin_providers(cfg: Mapping[str, Any]) -> list[Provider]:
    """dishka Providers a plugin ships, listed in its manifest:

    providers:
      mimir: redsun_mimir.providers:MimirProviders
    """
    ...


# ==========================================================================
# What an author writes: mimir's own container, rewritten
# ==========================================================================
#
# from redsun_mimir.device import MockLightDevice
# from redsun_mimir.device.mmcore import MMDemoCamera, MMDemoXYStage, MMDemoZStage
# from redsun_mimir.presenter import (AcquisitionPresenter, DetectorPresenter,
#                                     LightPresenter, MedianPresenter, MotorPresenter)
# from redsun_mimir.view import (AcquisitionView, DetectorView, ImageView,
#                                LightView, MotorView)
#
# class MimirSimulator(QtAppContainer):
#     config = Path(__file__).parent / "full_configuration.yaml"
#     providers = [MimirProviders()]
#
#     mmcamera:  A[MMDemoCamera,        FromConfig("camera1")]
#     XY:        A[MMDemoXYStage,       FromConfig("xy-motor")]
#     Z:         A[MMDemoZStage,        FromConfig("z-motor")]
#     laser:     A[MockLightDevice,     Declare()]
#     led:       A[MockLightDevice,     Declare()]
#
#     storage_ctrl: A[StoragePresenter,     Declare()]
#     median_ctrl:  A[MedianPresenter,      Declare()]
#     det_ctrl:     A[DetectorPresenter,    Declare()]
#     acq_ctrl:     A[AcquisitionPresenter, Declare()]
#     light_ctrl:   A[LightPresenter,       Declare()]
#     motor_ctrl:   A[MotorPresenter,       Declare()]
#
#     acq_widget:     A[AcquisitionView, Declare()]
#     img_widget:     A[ImageView,       Declare()]
#     det_widget:     A[DetectorView,    Declare()]
#     light_widget:   A[LightView,       Declare()]
#     motor_widget:   A[MotorView,       Declare()]
#     storage_widget: A[StorageView,     Declare()]
#
#     def wire(self) -> None:
#         wire_detector(self, self.det_ctrl, self.det_widget, self.img_widget)
#         ...
#
# Against the current version: `from_config=` disappears from 14 of 17
# declarations because the attribute name is the config key, the
# `config=_CONFIG` class keyword becomes a plain assignment, and the three
# declare_* imports become one `Annotated`.
#
# `Declare()` with no arguments is noise. Two ways out, both cheap:
#   - accept a bare annotation, `storage_ctrl: StoragePresenter`, and treat any
#     annotation whose type is a device/presenter/view as a declaration. Costs
#     the ability to have an annotated attribute of those types that is *not* a
#     component, which no current code wants.
#   - keep the marker but make it a singleton: `A[StoragePresenter, DECLARE]`.
# The first is the better trade and makes the common line as short as it gets.
