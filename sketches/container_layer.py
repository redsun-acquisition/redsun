# ruff: noqa
"""The container layer under Option 1, sketched end to end.

Replaces: AppContainer.build phases 3 and 5, VirtualContainer.provide/require/
try_require/_provided, ProviderKey, IsProvider, IsInjectable.

Not executed and not import-clean: dishka is not installed here, and the
redsun imports are the shapes this would need, not the ones that exist today.
"""

from __future__ import annotations

import inspect
import logging
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    NewType,
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
    from dishka import Container
    from ophyd_async.core import Device

    from redsun.device import DeviceMap

logger = logging.getLogger("redsun")


class _Declaration:
    """One declared component, resolved to a dishka key.

    `key` is a NewType synthesized from the component name, so two instances
    of one class stay distinct. `cfg_kwargs` are the config-file and inline
    keyword arguments: they are data, never dependencies, and are bound into
    the factory rather than offered to the graph.
    """

    __slots__ = ("cfg_kwargs", "cls", "instance", "key", "kind", "name")

    def __init__(self, cls: type, name: str, kind: str, cfg_kwargs: dict[str, Any]):
        self.cls = cls
        self.name = name
        self.kind = kind
        self.cfg_kwargs = cfg_kwargs
        self.key = NewType(name, cls)
        self.instance: Any = None


def _optional_arg(hint: Any) -> Any | None:
    """Return X for `X | None` and `Optional[X]`, else None."""
    if get_origin(hint) not in (Union, UnionType):
        return None
    args = [a for a in get_args(hint) if a is not type(None)]
    return args[0] if len(args) == 1 else None


def _injectable(cls: type, cfg_kwargs: dict[str, Any]) -> dict[str, Any]:
    """Constructor parameters the graph is responsible for.

    Excludes `name` (identity, bound by the framework), anything the config
    supplied, and **kwargs. Everything left must carry an annotation.
    """
    hints = get_type_hints(cls.__init__, include_extras=True)
    sig = inspect.signature(cls)
    out: dict[str, Any] = {}
    for pname, param in sig.parameters.items():
        if pname in ("self", "name") or pname in cfg_kwargs:
            continue
        if param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
            continue
        if pname not in hints:
            raise TypeError(
                f"{cls.__name__}.{pname} has no annotation; the container "
                "cannot tell what to inject"
            )
        out[pname] = hints[pname]
    return out


def _component_factory(
    decl: _Declaration, available: frozenset[Any]
) -> Callable[..., Any]:
    """Build the callable dishka will inspect and call.

    dishka resolves by reading annotations, so the generated factory advertises
    exactly the parameters the graph should fill. Optional parameters are
    decided here, statically: if nothing in the assembled provider set offers
    the type, None is closed over and the parameter is never shown to dishka.
    This is what replaces try_require, and it needs no exception handling at
    resolution time.
    """
    wanted = _injectable(decl.cls, decl.cfg_kwargs)

    required: dict[str, Any] = {}
    absent: dict[str, None] = {}
    for pname, hint in wanted.items():
        inner = _optional_arg(hint)
        if inner is None:
            required[pname] = hint
        elif inner in available:
            required[pname] = inner
        else:
            absent[pname] = None

    def factory(**deps: Any) -> Any:
        return decl.cls(decl.name, **decl.cfg_kwargs, **absent, **deps)

    factory.__name__ = f"build_{decl.name}"
    factory.__annotations__ = {**required, "return": decl.key}
    return factory


def _provided_keys(providers: list[Provider]) -> frozenset[Any]:
    """Types the assembled providers can supply.

    Reads Provider.factories/.aliases/.context_vars, which is dishka internal
    surface. If that proves unstable, the fallback is an explicit
    `optional=[...]` argument on the declaration.
    """
    keys: set[Any] = set()
    for provider in providers:
        for factory in provider.factories:
            keys.add(factory.provides.type_hint)
        for alias in provider.aliases:
            keys.add(alias.provides.type_hint)
        for var in provider.context_vars:
            keys.add(var.provides.type_hint)
    return frozenset(keys)


class AppContainer:
    """Application container. Declaration collection is unchanged; the build
    is four phases instead of six.
    """

    providers: ClassVar[list[Provider]] = []
    _declarations: ClassVar[dict[str, _Declaration]] = {}

    def __init__(self, *, session: str = "Redsun", frontend: str = "pyqt") -> None:
        self._bus = VirtualContainer()
        self._di: Container | None = None
        self._devices: dict[str, Device] = {}
        self._is_built = False

    def build(self) -> AppContainer:
        """Instantiate everything.

        1. Devices. Built here, not by dishka: a device that fails to build is
           logged and skipped, and a graph edge cannot be skipped.
        2. Register. One factory per declaration, plus the framework's own
           objects, on a single flat provider.
        3. Resolve. dishka orders the component graph; the loop below only
           forces each declared component to exist.
        4. Wire. Every instance exists, so connections can be checked.
        """
        self._devices = self._build_devices()

        framework = Provider(scope=Scope.APP)
        framework.provide(lambda: self._bus, provides=VirtualContainer)
        framework.provide(lambda: DeviceMap(self._devices), provides=DeviceMap)

        providers = [framework, *self.providers]
        available = _provided_keys(providers)

        components = Provider(scope=Scope.APP)
        for decl in self._declarations.values():
            components.provide(
                _component_factory(decl, available),
                provides=decl.key,
                scope=Scope.APP,
            )
        self._register_class_aliases(components)

        self._di = make_container(components, *providers)

        for decl in self._declarations.values():
            decl.instance = self._di.get(decl.key)
            self._validate(decl)

        self._bus._set_components(
            {d.name: d.instance for d in self._declarations.values()}
        )
        self.wire()
        self._apply_wiring_config()
        self._is_built = True
        return self

    def _register_class_aliases(self, provider: Provider) -> None:
        """Let a component be asked for by its class when that is unambiguous.

        One MotorPresenter in the app: another component may annotate
        `motor: MotorPresenter`. Two of them: the plain class is ambiguous, so
        no alias is registered and asking by class fails at resolution with a
        message naming both instances.
        """
        by_class: dict[type, list[_Declaration]] = {}
        for decl in self._declarations.values():
            by_class.setdefault(decl.cls, []).append(decl)
        for cls, decls in by_class.items():
            if len(decls) == 1:
                provider.alias(source=decls[0].key, provides=cls)
            else:
                logger.debug(
                    "%s is declared as %s; it can only be injected by name",
                    cls.__name__,
                    ", ".join(d.name for d in decls),
                )

    def _validate(self, decl: _Declaration) -> None:
        """Instance-level gate. Unchanged in spirit: protocol compliance is
        only knowable once __init__ has run.
        """
        protocol = PPresenter if decl.kind == "presenter" else PView
        if not isinstance(decl.instance, protocol):
            raise TypeError(
                f"{type(decl.instance).__name__!r} ({decl.kind} {decl.name!r}) "
                f"does not implement {protocol.__name__}"
            )

    def _build_devices(self) -> dict[str, Device]: ...
    def wire(self) -> None: ...
    def _apply_wiring_config(self) -> None: ...

    @classmethod
    def from_config(cls, config_path: str) -> AppContainer:
        """Config-driven path. Discovery is unchanged; only the registration
        target differs. Declarations are data either way, so the YAML route
        and the class-body route produce the same _Declaration objects.
        """
        config, plugin_types = cls._load_configuration(config_path)

        declarations: dict[str, _Declaration] = {}
        for kind, group in (("presenter", "presenters"), ("view", "views")):
            for name, plugin_cls in plugin_types[group].items():
                cfg = {
                    k: v
                    for k, v in config.get(group, {}).get(name, {}).items()
                    if k not in ("plugin_name", "plugin_id")
                }
                declarations[name] = _Declaration(plugin_cls, name, kind, cfg)

        instance = cls(
            session=config.get("session", "Redsun"),
            frontend=config.get("frontend", "pyqt"),
        )
        type(instance)._declarations = declarations
        instance.providers = [*cls.providers, *cls._load_plugin_providers(config)]
        return instance

    @classmethod
    def _load_configuration(cls, path: str) -> tuple[dict[str, Any], Any]: ...

    @classmethod
    def _load_plugin_providers(cls, config: dict[str, Any]) -> list[Provider]:
        """Plugins that ship services declare them in their manifest:

        providers:
          services: my_plugin.di:MyPluginServices
        """
        ...


# What this deletes
# -----------------
#   redsun/virtual/_protocols.py                             41 lines, whole file
#   VirtualContainer.provide/require/try_require/_provided   ~55 lines
#   ProviderKey and PATH_PROVIDER                            ~10 lines
#   build() phases 3 and 5 (register_providers, inject)      ~10 lines
#   _PresenterField/_ViewField/_DeviceField                  ~50 lines, if the
#                                                            annotated form in
#                                                            option4 is taken
#
# What this adds
# --------------
#   _Declaration, _component_factory, _injectable,
#   _optional_arg, _provided_keys, _register_class_aliases   ~110 lines
#
# Net line count is close to a wash. The concept count is not: two protocols,
# a key type, two build phases and three lookup methods stop existing, and
# "which phase am I allowed to ask for this in" stops being a question an
# author has to answer.
