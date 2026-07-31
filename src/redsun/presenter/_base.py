from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from ophyd_async.core import Device

__all__ = ["PPresenter", "Presenter"]


@runtime_checkable
class PPresenter(Protocol):  # pragma: no cover
    """Presenter protocol class.

    Members are declared as **read-only properties**: the framework only
    ever reads them, so implementers may satisfy the protocol with plain
    instance attributes, class attributes, or properties, and ``devices``
    may be any ``Mapping`` subtype (e.g. a plain ``dict``). Declaring them
    read-write would force implementers to expose settable, invariantly
    typed attributes, ruling out property-based classes.

    Notes
    -----
    Access to the virtual container is optional and should be acquired
    by implementing [`IsProvider`][redsun.virtual.IsProvider] or
    [`IsInjectable`][redsun.virtual.IsInjectable].

    Compliance is enforced at build time via ``isinstance`` - class-level
    checks cannot see attributes assigned in ``__init__``.
    """

    @property
    def name(self) -> str:
        """Identity key of the presenter."""
        ...

    @property
    def devices(self) -> Mapping[str, Device]:
        """Reference to the devices used in the presenter."""
        ...


class Presenter(ABC):
    """Presenter base class.

    Deliberately does **not** inherit [`PPresenter`][redsun.presenter.PPresenter]:
    the protocol's read-only property descriptors would shadow the instance
    attributes assigned here. Instances satisfy the protocol structurally - which is also how any non-ABC presenter is expected to comply.

    Parameters
    ----------
    name : str
        Identity key of the presenter. Passed as positional-only argument.
    devices : Mapping[str, redsun.device.Device]
        Reference to the devices used in the presenter.
    kwargs : Any, optional
        Additional keyword arguments for presenter subclasses.
    """

    name: str
    devices: Mapping[str, Device]

    @abstractmethod
    def __init__(
        self,
        name: str,
        devices: Mapping[str, Device],
        /,
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.devices = devices
        super().__init__(**kwargs)
