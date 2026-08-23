# ruff: noqa
"""The same task, written by a component author under each option.

Task: ship a presenter that owns a shared service, and a view that consumes
that service but must still work in an application that does not have it.
That is exactly StoragePresenter + StorageView today, so the baseline is real
code rather than an invented strawman.
"""

from __future__ import annotations

from typing import Any

# ==========================================================================
# BASELINE: what an author writes today
# ==========================================================================

import dependency_injector.providers as dip

from redsun.presenter import Presenter
from redsun.storage import SessionPathProvider
from redsun.view.qt import QtView
from redsun.virtual import VirtualContainer, slot

# 1. a key object, defined at module level and re-exported publicly so that
#    consumers in other packages can import it
PATH_PROVIDER = dip.Dependency(instance_of=SessionPathProvider)


class StoragePresenter(Presenter):
    def __init__(
        self,
        name: str,
        devices: Any,  # 2. mandatory positional this class never uses
        /,
        base_dir: str | None = None,
        max_digits: int = 5,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, devices, **kwargs)  # 3. forward the unused one
        self._base_dir = base_dir
        self._max_digits = max_digits
        # 4. the service cannot be built here: the session name is not
        #    available until a later phase
        self._provider: SessionPathProvider | None = None

    # 5. a guard property, because the attribute is legitimately None for part
    #    of the object's life, and the author has to explain that in prose
    @property
    def path_provider(self) -> SessionPathProvider:
        if self._provider is None:
            raise RuntimeError(
                "The path provider is created during 'register_providers'; "
                "it is not available before the container build reaches that "
                "phase."
            )
        return self._provider

    # 6. a lifecycle hook, plus knowledge of when it runs relative to __init__,
    #    to wiring, and to inject_dependencies
    def register_providers(self, container: VirtualContainer) -> None:
        self._provider = SessionPathProvider(
            base_dir=self._base_dir,
            session=container.session,
            max_digits=self._max_digits,
        )
        container.provide(PATH_PROVIDER, self._provider)

    @slot
    def set_plan(self, plan_name: str) -> None:
        self.path_provider.set_plan(plan_name)


class StorageView(QtView):
    def __init__(self, name: str, /, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self._provider: SessionPathProvider | None = None  # 7. nullable again
        ...

    # 8. a second lifecycle hook, and the author must know it runs after
    #    register_providers or the key will not be bound yet
    def inject_dependencies(self, container: VirtualContainer) -> None:
        provider = container.try_require(PATH_PROVIDER)  # 9. import the key
        if provider is None:
            self._placeholder()
            return
        self._provider = provider
        container.subscribe(provider.signals.base_dir, self.update_base_dir)

    def _placeholder(self) -> None: ...

    @slot
    def update_base_dir(self, reading: dict[str, Any]) -> None: ...


# Author-visible concepts: 9. Of those, 6 exist only because there is no
# injection: the key object, the unused positional, the nullable attribute,
# the guard property, and the two hooks with their ordering rule.


# ==========================================================================
# OPTION 1 / OPTION 4: the author writes a constructor
# ==========================================================================

from dishka import Provider, Scope, provide


class Services(Provider):
    """Only the author who *introduces* a shared service writes this."""

    scope = Scope.APP

    @provide
    def paths(self, bus: VirtualContainer) -> SessionPathProvider:
        return SessionPathProvider(session=bus.session)


class StoragePresenterV1(Presenter):
    def __init__(self, name: str, /, paths: SessionPathProvider, max_digits: int = 5):
        super().__init__(name)
        self._paths = paths

    @slot
    def set_plan(self, plan_name: str) -> None:
        self._paths.set_plan(plan_name)


class StorageViewV1(QtView):
    def __init__(
        self,
        name: str,
        /,
        bus: VirtualContainer,
        paths: SessionPathProvider | None = None,
    ) -> None:
        super().__init__(name)
        if paths is None:
            self._placeholder()
            return
        bus.subscribe(paths.signals.base_dir, self.update_base_dir)

    def _placeholder(self) -> None: ...

    @slot
    def update_base_dir(self, reading: dict[str, Any]) -> None: ...


# Author-visible concepts: 3 (typed ctor params, `X | None` for optional,
# @slot). The service author adds a 4th: the dishka Provider. No key, no
# hooks, no phase order, no nullable-until-later attribute, no guard property.


# ==========================================================================
# The Provider is the one remaining piece of boilerplate. It can be sugar.
# ==========================================================================


def service(cls: type) -> type:
    """Register a class as an APP-scoped service with ctor injection.

    Collapses the five-line Provider subclass to one line for the common case.
    Authors who need scopes, finalization or a factory function still write a
    Provider; nothing is taken away.
    """
    ...


@service
class SessionPathProviderV1:
    def __init__(self, bus: VirtualContainer) -> None: ...


# Author-visible concepts for a service author: 1.


# ==========================================================================
# OPTION 2: the author writes the wiring the framework used to write
# ==========================================================================


class AppProviderV2(Provider):
    scope = Scope.APP

    @provide
    def paths(self, bus: VirtualContainer) -> SessionPathProvider:
        return SessionPathProvider(session=bus.session)

    # the component's *name* is now the author's responsibility, repeated here
    # and again in every wiring path that mentions it
    @provide
    def paths_ctrl(self, paths: SessionPathProvider) -> StoragePresenterV1:
        return StoragePresenterV1("paths_ctrl", paths, max_digits=6)


# and the author writes this too, per component, with untyped locals:
#
#   di = make_container(AppProviderV2())
#   paths_ctrl = di.get(StoragePresenterV1)
#   storage_ui = di.get(StorageViewV1)
#   bus.connect(paths_ctrl.sig_plan_set, storage_ui.update_base_dir)
#
# Author-visible concepts: 6, and two of them (NewType-per-instance, manual
# get() ordering) are framework work that has been handed to the user.


# ==========================================================================
# OPTION 3: identical to Option 1 for the author, and can go one step lower
# ==========================================================================
#
# Same constructors as Option 1. Because redsun owns the resolver, the service
# registration step can be implicit: any annotated parameter whose type is a
# class with resolvable dependencies gets constructed, no declaration at all.
#
#   class StoragePresenterV3(Presenter):
#       def __init__(self, name: str, /, paths: SessionPathProvider): ...
#
#   # nothing else. SessionPathProvider is constructed because something
#   # asked for it and its own __init__ only needs things already resolvable.
#
# Author-visible concepts: 2. Lowest of any option.
#
# The cost is that "resolvable" is now a rule redsun defines, documents and
# debugs, and implicit construction has a well-known failure mode: a typo in
# an annotation silently constructs the wrong thing instead of failing.
# dishka's explicitness is a deliberate choice, not an oversight.
