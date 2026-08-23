# ruff: noqa
"""The application container."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Generic, NewType, TypeVar

import yaml
from dishka import AnyOf, Provider, make_container
from typing_extensions import TypeForm

from redsun.aio import run_coro
from redsun.presenter import PPresenter
from redsun.view import PView
from redsun.virtual import VirtualContainer

from . import _declarations as declarations
from . import _factories as factories
from . import _provides
from ._scopes import AppScope

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Mapping

    from dishka import Container
    from ophyd_async.core import Device, DeviceMap

    from redsun.virtual import CallbackType

logger = logging.getLogger("redsun")

DocumentCallbacks = NewType("DocumentCallbacks", "dict[str, CallbackType]")
"""The document callbacks a session offers, once every component exists.

Asking for this postpones a component to the WIRED stage.
"""


class Frontend:
    """Marker for the toolkit an application is built against."""


class Qt(Frontend): ...


FE = TypeVar("FE", bound=Frontend)


class AppContainer(Generic[FE]):
    """Declarative application container.

    Components are declared as annotations:

    ```python
    class MyApp(AppContainer[Qt]):
        config = "session.yaml"
        providers = [MyServices()]

        motor: MMDemoXYStage
        motor_ctrl: MotorPresenter
        motor_widget: Annotated[MotorView, Declare(step_size=5.0)]

        def wire(self) -> None:
            self.connect(self.motor_ctrl.sig_moved, self.motor_widget.update)
    ```

    The attribute name is the component name and the configuration key;
    `Alias` and `FromConfig` override each. Reading a declared attribute on a
    built container gives the built instance, typed by its annotation.
    """

    config: ClassVar[str | Path | Mapping[str, Any] | None] = None
    providers: ClassVar[list[Provider]] = []

    def __init__(self) -> None:
        self._bus = VirtualContainer()
        self._di: Container | None = None
        self._scope: Any = None
        self._declarations: dict[str, declarations.Declaration] = {}
        self._devices: dict[str, Device] = {}
        self._is_built = False

    def __getattr__(self, name: str) -> Any:
        """Resolve a declared component. Type checkers use the annotation."""
        try:
            return self._declarations[name].instance
        except KeyError:
            raise AttributeError(
                f"{type(self).__name__!r} declares no component {name!r}"
            ) from None

    @property
    def devices(self) -> Mapping[str, Device]:
        """The devices that built successfully."""
        return dict(self._devices)

    @property
    def virtual_container(self) -> VirtualContainer:
        """The signal bus and document-callback registry."""
        return self._bus

    @property
    def is_built(self) -> bool:
        """Whether `build` has completed."""
        return self._is_built

    def build(self) -> AppContainer[FE]:
        """Instantiate the application.

        Devices are built here rather than by the graph: one that fails is
        logged and skipped, and a graph edge cannot be skipped. Everything
        after that is ordered by dishka, stage by stage.
        """
        if self._is_built:
            logger.warning("Container already built, skipping rebuild")
            return self

        config = _read_config(self.config)
        self._bus._set_configuration(config)
        self._declarations = declarations.read(type(self), config)

        self._build_devices()

        providers = [
            self._runtime_provider(),
            *self.providers,
            *_plugin_providers(config),
        ]

        # stages first: a component's stage depends on its dependencies', and a
        # shared value's stage is its owner's, so both settle together
        stages: dict[TypeForm[Any], AppScope] = _framework_stages()
        factories.resolve_scopes(self._components(), stages)

        components = Provider()
        shared: dict[TypeForm[Any], str] = {}
        for decl in self._components():
            components.provide(
                factories.factory(decl),
                provides=AnyOf[decl.key, decl.cls] if self._unique(decl) else decl.key,
                scope=decl.scope,
            )
            # a component's own @provides methods, bound to this instance
            _provides.register(components, decl, decl.scope, shared)

        # `X | None` resolves to the instance or to None, decided by Has(X)
        factories.register_optionals(components, self._components(), AppScope.COMPONENT)

        self._di = make_container(components, *providers, scopes=AppScope)

        with self._di(scope=AppScope.COMPONENT) as component_scope:
            self._resolve(component_scope, AppScope.COMPONENT)
            wired_scope = component_scope(scope=AppScope.WIRED).__enter__()
            self._resolve(wired_scope, AppScope.WIRED)
            # held open for the life of the application: leaving the scope
            # releases everything created in it
            self._scope = wired_scope

        self._bus._set_components(
            {d.name: d.instance for d in self._components() if d.instance is not None}
        )
        self.wire()
        self._apply_wiring_config(config)
        self._is_built = True
        logger.info(
            f"Container built: {len(self._devices)} devices, "
            f"{sum(1 for d in self._components() if d.kind == 'presenter')} presenters, "
            f"{sum(1 for d in self._components() if d.kind == 'view')} views"
        )
        return self

    def wire(self) -> None:
        """Connect the signals and slots of built components.

        Every component exists by the time this runs. The default connects
        nothing.
        """

    def connect(self, signal: Any, slot: Any, *, thread: Any = None) -> Any:
        """Connect a signal to a slot, recording the link for teardown."""
        return self._bus.connect(signal, slot, thread=thread)

    def connect_devices(self, mock: bool = False) -> None:
        """Connect every built device through ophyd-async."""
        if not self._is_built:
            raise RuntimeError("Call build() before connect_devices()")

        async def connect_all() -> None:
            import asyncio

            await asyncio.gather(
                *[device.connect(mock=mock) for device in self._devices.values()]
            )

        run_coro(connect_all())

    def shutdown(self) -> None:
        """Tear the application down.

        Leaving the WIRED scope finalizes every component whose factory is a
        generator, in reverse creation order.
        """
        if not self._is_built:
            return
        self._bus.disconnect_all()
        if self._scope is not None:
            self._scope.close()
            self._scope = None
        self._is_built = False

    def _components(self) -> list[declarations.Declaration]:
        return [d for d in self._declarations.values() if d.kind != "device"]

    def _runtime_provider(self) -> Provider:
        """Framework objects every component may ask for by type.

        `DocumentCallbacks` is the odd one out: it is a snapshot of a registry
        other components populate as they are built, so it is only legal once
        they all exist. Declaring it at WIRED is what makes asking for it
        postpone the component that asks.
        """
        provider = Provider(scope=AppScope.RUNTIME)
        provider.provide(lambda: self._bus, provides=VirtualContainer)
        provider.provide(lambda: DeviceMap(self._devices), provides=DeviceMap)
        provider.provide(
            factories.synthesize(
                lambda **deps: DocumentCallbacks(dict(deps["bus"].callbacks)),
                {"bus": VirtualContainer},
                DocumentCallbacks,
                "document_callbacks",
            ),
            scope=AppScope.WIRED,
        )
        return provider

    def _build_devices(self) -> None:
        for decl in self._declarations.values():
            if decl.kind != "device":
                continue
            try:
                self._devices[decl.name] = decl.cls(decl.name, **decl.cfg_kwargs)
                decl.instance = self._devices[decl.name]
            except Exception as e:  # noqa: BLE001 - a missing device must not abort the app
                logger.error(f"Failed to build device '{decl.name}': {e}")

    def _resolve(self, scope: Container, stage: AppScope) -> None:
        for decl in self._components():
            if decl.scope is not stage:
                continue
            decl.instance = scope.get(decl.key)
            self._validate(decl)
            self._bus.register_signals(decl.instance, name=decl.name)

    def _unique(self, decl: declarations.Declaration) -> bool:
        """Whether *decl*'s class may also serve as a key.

        A class declared once can be injected by its own type. Declared twice
        it is ambiguous, so only the per-name key is registered and asking by
        class fails with dishka's own missing-factory message.
        """
        others = [d for d in self._components() if d.cls is decl.cls]
        if len(others) == 1:
            return True
        logger.debug(
            f"{decl.cls.__name__} is declared as "
            f"{', '.join(d.name for d in others)}; it can only be injected by name"
        )
        return False

    def _validate(self, decl: declarations.Declaration) -> None:
        protocol = PPresenter if decl.kind == "presenter" else PView
        if not isinstance(decl.instance, protocol):
            raise TypeError(
                f"{type(decl.instance).__name__!r} ({decl.kind} {decl.name!r}) "
                f"does not implement {protocol.__name__}"
            )

    def _apply_wiring_config(self, config: Mapping[str, Any]) -> None:
        for rule in config.get("wiring", []):
            self._bus.connect_paths(rule["from"], rule["to"])


def _framework_stages() -> dict[TypeForm[Any], AppScope]:
    """The stages the framework's own dependencies are available at.

    Seeds the fixpoint in `resolve_scopes`. Only the framework's keys need to
    be listed: everything else settles from these.
    """
    return {
        VirtualContainer: AppScope.RUNTIME,
        DeviceMap: AppScope.RUNTIME,
        DocumentCallbacks: AppScope.WIRED,
    }


def _read_config(source: Any) -> Mapping[str, Any]:
    """A path, or a mapping straight from a test. Read once, at build."""
    if source is None:
        return {}
    if isinstance(source, (str, Path)):
        with open(source) as fh:
            return dict(yaml.safe_load(fh) or {})
    return source


def _plugin_providers(config: Mapping[str, Any]) -> list[Provider]:
    """dishka providers the configured plugins ship, from their manifests."""
    ...


__all__ = ["AppContainer", "Frontend", "Qt"]
