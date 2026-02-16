from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from sunflare.device import Device
from sunflare.presenter import Presenter
from sunflare.view import View

if TYPE_CHECKING:
    from sunflare.virtual import VirtualBus

__all__ = ["DeviceComponent", "PresenterComponent", "ViewComponent"]

T = TypeVar("T")


class ComponentBase(Generic[T]):
    """Generic base class for components."""

    __slots__ = ("cls", "name", "kwargs", "_instance")

    def __init__(self, cls: type[T], name: str, /, **kwargs: Any) -> None:
        self.cls = cls
        self.name = name
        self.kwargs = kwargs
        self._instance: T | None = None

    @property
    def instance(self) -> T:
        if self._instance is None:
            raise RuntimeError(
                f"Component {self.name} has not been instantiated yet. Call 'build' first."
            )
        return self._instance

    def __repr__(self) -> str:
        status = "built" if self._instance is not None else "pending"
        return f"{self.__class__.__name__}({self.name!r}, {status})"


class DeviceComponent(ComponentBase[Device]):
    """Device component wrapper."""

    def build(self) -> Device:
        """Build the device instance."""
        self._instance = self.cls(self.name, **self.kwargs)
        return self.instance


class PresenterComponent(ComponentBase[Presenter]):
    """Presenter component wrapper."""

    def build(self, devices: dict[str, Device], virtual_bus: VirtualBus) -> Presenter:
        """Build the presenter instance."""
        self._instance = self.cls(devices, virtual_bus, **self.kwargs)
        return self.instance


class ViewComponent(ComponentBase[View]):
    """View component wrapper."""

    def build(self, virtual_bus: VirtualBus) -> View:
        """Build the view instance."""
        self._instance = self.cls(virtual_bus, **self.kwargs)
        return self.instance
