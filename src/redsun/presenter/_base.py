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
    """Protocol of a presenter component.

    Members are read-only properties, so instance attributes, class attributes
    or properties satisfy them, and ``devices`` may be any ``Mapping``, such
    as a ``dict``.

    Notes
    -----
    A presenter reaches the virtual container by implementing
    [`IsProvider`][redsun.virtual.IsProvider] or
    [`IsInjectable`][redsun.virtual.IsInjectable].

    Checked with ``isinstance`` on the built instance, since attributes
    assigned in ``__init__`` do not exist on the class.
    """

    @property
    def name(self) -> str:
        """Identity key of the presenter."""
        ...

    @property
    def devices(self) -> Mapping[str, Device]:
        """The session's devices."""
        ...


class Presenter(ABC):
    """Base presenter class.

    Does not inherit [`PPresenter`][redsun.presenter.PPresenter], whose
    read-only properties would shadow the instance attributes set here.
    Instances satisfy the protocol by shape, like any other presenter.

    Parameters
    ----------
    name : str
        Identity key of the presenter, positional-only.
    devices : Mapping[str, ophyd_async.core.Device]
        The session's devices.
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
