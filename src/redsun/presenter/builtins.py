"""Built-in, reusable presenter components.

These presenters ship with redsun and can be used directly in declarative
containers (``declare_presenter``) or referenced from a YAML configuration
via the ``redsun`` plugin manifest (``plugin_name: redsun``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from dependency_injector import providers

from redsun.log import Loggable
from redsun.presenter import Presenter
from redsun.storage import SessionPathProvider
from redsun.utils import find_signals

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ophyd_async.core import Device

    from redsun.virtual import VirtualContainer

__all__ = ["StoragePresenter"]

_RESET_PLAN = "unknown"


class StoragePresenter(Presenter, Loggable):
    """Application-level control point for the session path provider.

    Owns the [`SessionPathProvider`][redsun.storage.SessionPathProvider] and
    exposes it on the virtual container as the ``path_provider`` provider, so
    every view and presenter resolves the same instance. Storage instances get
    it at construction; devices only ever see
    [`BaseStorage`][redsun.storage.BaseStorage].

    Wiring:

    - ``sig_pre_launch_notify`` (str) -> ``set_plan``: filenames adopt the plan
      name of the upcoming run.
    - ``sig_plan_done`` -> plan resets to ``"unknown"``, so stray bursts are not
      attributed to a finished plan.

    Parameters
    ----------
    name : str
        Identity key of the presenter.
    devices : Mapping[str, Device]
        Available devices (unused; accepted for the presenter contract).
    base_dir : str | None
        Base directory for storage paths. YAML-friendly string; ``~`` is
        expanded. Defaults to the provider's own default
        (``~/redsun-storage``).
    max_digits : int
        Zero-padding width for the burst counter. Defaults to 5.
    """

    def __init__(
        self,
        name: str,
        devices: Mapping[str, Device],
        /,
        base_dir: str | None = None,
        max_digits: int = 5,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, devices, **kwargs)
        self._base_dir = Path(base_dir).expanduser() if base_dir else None
        self._max_digits = max_digits
        self._provider: SessionPathProvider | None = None

    @property
    def path_provider(self) -> SessionPathProvider:
        """The owned provider. Available after ``register_providers``."""
        if self._provider is None:
            raise RuntimeError(
                "The path provider is created during 'register_providers'; "
                "it is not available before the container build reaches that "
                "phase."
            )
        return self._provider

    def register_providers(self, container: VirtualContainer) -> None:
        """Create the provider (session-scoped) and register it for DI."""
        self._provider = SessionPathProvider(
            base_dir=self._base_dir,
            session=container.session,
            max_digits=self._max_digits,
        )
        container.path_provider = providers.Object(self._provider)

    def inject_dependencies(self, container: VirtualContainer) -> None:
        """Connect plan lifecycle signals to the provider, if present."""
        sigs = find_signals(container, ["sig_pre_launch_notify", "sig_plan_done"])
        if "sig_pre_launch_notify" in sigs:
            sigs["sig_pre_launch_notify"].connect(self._on_pre_launch)
        if "sig_plan_done" in sigs:
            sigs["sig_plan_done"].connect(self._on_plan_done)

    def _on_pre_launch(self, plan_name: str) -> None:
        self.path_provider.set_plan(plan_name)

    def _on_plan_done(self) -> None:
        self.path_provider.set_plan(_RESET_PLAN)
