"""Presenters shipped with ``redsun``.

Declare them with ``declare_presenter``, or name them in a YAML configuration
through the ``redsun`` plugin manifest (``plugin_name: redsun``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from redsun.log import Loggable
from redsun.presenter import Presenter
from redsun.storage import PATH_PROVIDER, SessionPathProvider
from redsun.virtual import slot

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ophyd_async.core import Device

    from redsun.virtual import VirtualContainer

__all__ = ["StoragePresenter"]

_RESET_PLAN = "unknown"


class StoragePresenter(Presenter, Loggable):
    """Controls the session path provider for the application.

    Owns the [`SessionPathProvider`][redsun.storage.SessionPathProvider] and
    binds it to `PATH_PROVIDER` in the virtual container, so every view and
    presenter resolves the same instance. Storage instances receive it when
    constructed; devices only see [`BaseStorage`][redsun.storage.BaseStorage].

    The application connects two slots to whatever announces the plan
    lifecycle:

    - ``set_plan`` (str): filenames take the upcoming run's plan name;
    - ``reset_plan``: the plan name returns to ``"unknown"``, so bursts after a
      run are not filed under it.

    Parameters
    ----------
    name : str
        Identity key of the presenter.
    devices : Mapping[str, Device]
        The session's devices, unused.
    base_dir : str | None
        Base directory of storage paths, with ``~`` expanded. Defaults to the
        provider's default, ``~/redsun-storage``.
    max_digits : int
        Zero-padding width of the burst counter.
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
        """The owned provider, set by ``register_providers``."""
        if self._provider is None:
            raise RuntimeError(
                "The path provider is created during 'register_providers'; "
                "it is not available before the container build reaches that "
                "phase."
            )
        return self._provider

    def register_providers(self, container: VirtualContainer) -> None:
        """Create the session's provider and register it in the container."""
        self._provider = SessionPathProvider(
            base_dir=self._base_dir,
            session=container.session,
            max_digits=self._max_digits,
        )
        container.provide(PATH_PROVIDER, self._provider)

    @slot
    def set_plan(self, plan_name: str) -> None:
        """Use *plan_name* for the paths generated from now on."""
        self.path_provider.set_plan(plan_name)

    @slot
    def reset_plan(self) -> None:
        """Set the plan name back to its placeholder."""
        self.path_provider.set_plan(_RESET_PLAN)
