# ruff: noqa
"""Postponed injection via a custom dishka scope.

The AcquisitionPresenter case: it needs the document-callback registry, which
other components populate while they are built. It depends on "everything has
been built", which is a lifecycle stage, not a value - and a lifecycle stage
is exactly what a scope is.

Verified from the docs: dishka takes a custom BaseScope via `scopes=` on
make_container, nested scopes are entered with `with container(scope=...)`, and
a later-scope dependency may depend on earlier-scope ones. Container injection
(resolving lazily from inside a factory) is not documented, so nothing here
relies on it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated as A, Any, NewType

from dishka import BaseScope, Provider, make_container, new_scope, provide

from redsun.virtual import VirtualContainer

if TYPE_CHECKING:
    from collections.abc import Mapping

    from redsun.virtual import CallbackType


class AppScope(BaseScope):
    """The three stages a redsun build actually has.

    RUNTIME   framework objects: the bus, the config, the DeviceMap
    COMPONENT presenters and views
    WIRED     anything that needs every component to exist first
    """

    RUNTIME = new_scope("RUNTIME")
    COMPONENT = new_scope("COMPONENT")
    WIRED = new_scope("WIRED")


DocumentCallbacks = NewType("DocumentCallbacks", "Mapping[str, CallbackType]")


class FrameworkProvider(Provider):
    @provide(scope=AppScope.WIRED)
    def callbacks(self, bus: VirtualContainer) -> DocumentCallbacks:
        """A snapshot of the registry, legal only once components are built.

        Declaring it at WIRED is the whole mechanism: dishka refuses to build a
        COMPONENT-scoped factory that asks for a WIRED-scoped dependency, so
        the ordering rule is enforced by the container rather than policed by
        redsun.
        """
        return DocumentCallbacks(dict(bus.callbacks))


# ==========================================================================
# What the author writes: an annotation, and nothing else
# ==========================================================================


class AcquisitionPresenter:
    def __init__(
        self,
        name: str,
        /,
        devices: Any,
        callbacks: DocumentCallbacks,
        expected: frozenset[str] | None = None,
    ) -> None:
        self.engine = RunEngine()
        self.callback_tokens = {
            cb_name: self.engine.subscribe(cb)
            for cb_name, cb in callbacks.items()
            if expected is None or cb_name in expected
        }


class MimirSimulator(AppContainer):
    # no marker, no scope keyword, no lifecycle hook. This presenter is built
    # in the WIRED stage because of what it asks for.
    acq_ctrl: A[AcquisitionPresenter, Declare()]
    motor_ctrl: A[MotorPresenter, Declare()]
    motor_widget: A[MotorView, Declare()]


# ==========================================================================
# What the framework does
# ==========================================================================


def _scope_of(decl: Any, scopes_by_key: dict[Any, AppScope]) -> AppScope:
    """A component is built as late as its latest dependency requires.

    Computed from the declaration's injectable hints against the scopes the
    assembled providers declare, so an author never states a scope. Adding a
    WIRED-scoped parameter to a constructor moves that component to WIRED, and
    the components that depend on *it* move with it.
    """
    latest = AppScope.COMPONENT
    for hint in _injectable(decl.cls, decl.cfg_kwargs).values():
        scope = scopes_by_key.get(hint)
        if scope is not None and _is_later(scope, latest):
            latest = scope
    return latest


def build(self) -> None:
    di = make_container(components, *providers, scopes=AppScope)

    # RUNTIME objects live in the root container
    with di(scope=AppScope.COMPONENT) as component_scope:
        for decl in self._declarations.values():
            if decl.scope is AppScope.COMPONENT:
                decl.instance = component_scope.get(decl.key)

        with component_scope(scope=AppScope.WIRED) as wired_scope:
            for decl in self._declarations.values():
                if decl.scope is AppScope.WIRED:
                    decl.instance = wired_scope.get(decl.key)

            self._bus._set_components(...)
            self.wire()
            self._apply_wiring_config(cfg)
            self._scope = wired_scope  # held open for the life of the app


# The scope exits at application shutdown, not at the end of build. That is
# load-bearing: leaving the scope releases everything created in it.
#
# It also hands you something for free. dishka finalizes generator factories on
# scope exit, in reverse creation order:
#
#     @provide(scope=AppScope.COMPONENT)
#     def detector(self, devices: DeviceMap) -> Iterator[DetectorPresenter]:
#         presenter = DetectorPresenter("det_ctrl", devices)
#         yield presenter
#         presenter.shutdown()
#
# which is what AppContainer.shutdown does today by iterating components and
# isinstance-checking HasShutdown. That protocol could go the way of the other
# two - but it is a separate change and should not ride along with this one.


# ==========================================================================
# The alternative, if a third scope is judged too much
# ==========================================================================
#
# Make DocumentCallbacks a genuine dependency: the framework generates a
# factory whose parameters are every declared component except those that
# consume DocumentCallbacks themselves (which it can determine by scanning the
# declarations' hints, and must, or the graph cycles).
#
#     build.__annotations__ = {d.name: d.key for d in producers} | {
#         "return": DocumentCallbacks
#     }
#
# Exact ordering, no new scope, one flat container. The cost is a synthetic
# N-parameter factory that exists to express "after everything", which is what
# a scope says in one word. Prefer the scope.
