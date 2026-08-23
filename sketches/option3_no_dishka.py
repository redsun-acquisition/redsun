# ruff: noqa
"""Option 3: keep dependency-injector, fix the ergonomics in place.

No new dependency. `provide`/`require`/`try_require`/`ProviderKey` and the two
lifecycle protocols still go away; ctor annotations replace them. What you
hand-roll is the resolution graph.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Callable, TypeVar, get_type_hints

from redsun.presenter import Presenter
from redsun.storage import SessionPathProvider
from redsun.view.qt import QtView
from redsun.virtual import VirtualContainer

if TYPE_CHECKING:
    from redsun.device import DeviceMap

T = TypeVar("T")


class ServiceRegistry:
    """Type-keyed replacement for VirtualContainer._provided.

    A factory is a callable whose own annotations name what it needs, so
    services can depend on services.
    """

    def __init__(self) -> None:
        self._factories: dict[type, Callable[..., Any]] = {}
        self._instances: dict[type, Any] = {}
        self._resolving: set[type] = set()

    def register(self, factory: Callable[..., T], provides: type[T]) -> None:
        self._factories[provides] = factory

    def instance(self, value: T, provides: type[T]) -> None:
        self._instances[provides] = value

    def get(self, key: type[T]) -> T:
        if key in self._instances:
            return self._instances[key]
        if key not in self._factories:
            raise KeyError(f"nothing provides {key.__name__}")
        # this is the part dishka would own: cycle detection, caching,
        # topological order, and later on finalization and scopes
        if key in self._resolving:
            raise KeyError(f"dependency cycle through {key.__name__}")
        self._resolving.add(key)
        try:
            factory = self._factories[key]
            kwargs = {
                name: self.get(hint)
                for name, hint in _injectable_hints(factory).items()
            }
            value = factory(**kwargs)
        finally:
            self._resolving.discard(key)
        self._instances[key] = value
        return value

    def try_get(self, key: type[T]) -> T | None:
        try:
            return self.get(key)
        except KeyError:
            return None


def _injectable_hints(target: Callable[..., Any]) -> dict[str, type]:
    """Ctor or factory parameters that the registry should fill."""
    hints = get_type_hints(target)
    hints.pop("return", None)
    sig = inspect.signature(target)
    return {
        name: hints[name]
        for name, param in sig.parameters.items()
        if name in hints
        and param.kind is not inspect.Parameter.VAR_KEYWORD
        and name != "name"
    }


def resolve_component(
    cls: Callable[..., T],
    name: str,
    registry: ServiceRegistry,
    cfg_kwargs: dict[str, Any],
) -> T:
    """What _PresenterComponent.build becomes."""
    deps: dict[str, Any] = {}
    for param, hint in _injectable_hints(cls).items():
        if param in cfg_kwargs:
            continue
        optional = _strip_optional(hint)
        if optional is not None:
            deps[param] = registry.try_get(optional)
        else:
            deps[param] = registry.get(hint)
    return cls(name, **cfg_kwargs, **deps)


def _strip_optional(hint: type) -> type | None:
    """Return X for `X | None`, else None."""
    ...


class StoragePresenter(Presenter):
    def __init__(self, name: str, /, paths: SessionPathProvider, max_digits: int = 5):
        super().__init__(name)


class StorageView(QtView):
    def __init__(
        self,
        name: str,
        /,
        bus: VirtualContainer,
        paths: SessionPathProvider | None = None,
    ) -> None:
        super().__init__(name)


# Author-facing result is nearly identical to Option 1: same constructors,
# same disappearance of register_providers/inject_dependencies. The difference
# is who maintains ServiceRegistry.
#
# What you write yourself and would not write with dishka:
#   - caching, cycle detection, topological resolution   (above, and it is the
#     easy half: no scopes, no finalization, no context)
#   - anything resembling teardown ordering for services that hold resources
#   - generic factories, which the DevicePresenter[D] work wants later
#
# What you keep:
#   - no new runtime dependency
#   - full control over the optional-parameter rule, which dishka does not have
#   - dependency-injector stays for the config/wiring bits already using it
#
# Reasonable if the dependency count matters more than the sub-component
# roadmap. Otherwise you are writing a worse dishka.
