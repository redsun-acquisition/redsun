from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar

from sunflare.device import Device
from sunflare.presenter import Presenter
from sunflare.view import View

if TYPE_CHECKING:
    from sunflare.virtual import VirtualContainer


T = TypeVar("T")


class _ComponentField:
    """Internal sentinel returned by `component`.

    Stores the component class, layer assignment, and keyword arguments
    until the `AppContainerMeta` metaclass resolves them into concrete
    component wrappers.
    """

    __slots__ = ("cls", "layer", "alias", "from_config", "kwargs")

    def __init__(
        self,
        cls: type,
        layer: Literal["device", "presenter", "view"],
        alias: str | None,
        from_config: str | None,
        kwargs: dict[str, Any],
    ) -> None:
        self.cls = cls
        self.layer = layer
        self.alias = alias
        self.from_config = from_config
        self.kwargs = kwargs


def device(
    cls: type,
    /,
    alias: str | None = None,
    from_config: str | None = None,
    **kwargs: Any,
) -> Any:
    """Declare a component as a device layer field.

    A device can be declared inside the body of an `AppContainer`:

    >>> class MyApp(AppContainer):
    ...     motor = device(MyMotor, axis=["X"])

    The container will create an instance of `MyMotor` with the specified kwargs when the
    container is built. The attribute name `motor` will be used as the device `name` argument.

    Parameters
    ----------
    cls : type
        The component class to instantiate.
    alias : str | None
        Override the component name. Takes priority over the attribute name.
    from_config : str | None
        Key to look up in the configuration file's ``devices`` section.
    **kwargs : Any
        Additional keyword arguments forwarded to the component constructor.
    """
    return _ComponentField(
        cls=cls, layer="device", alias=alias, from_config=from_config, kwargs=kwargs
    )


def view(cls: type, /, alias: str | None = None, from_config: str | None = None, **kwargs: Any) -> Any:
    """Declare a component as a view layer field.

    >>> class MyApp(AppContainer):
    ...     ui = view(MyView)

    Parameters
    ----------
    cls : type
        The component class to instantiate.
    alias : str | None
        Override the component name. Takes priority over the attribute name.
    from_config : str | None
        Key to look up in the configuration file's ``views`` section.
    **kwargs : Any
        Additional keyword arguments forwarded to the component constructor.
    """
    return _ComponentField(
        cls=cls, layer="view", alias=alias, from_config=from_config, kwargs=kwargs
    )


def presenter(cls: type, /, alias: str | None = None, from_config: str | None = None, **kwargs: Any) -> Any:
    """Declare a component as a presenter layer field.

    >>> class MyApp(AppContainer):
    ...     ctrl = presenter(MyCtrl, gain=1.0)

    Parameters
    ----------
    cls : type
        The component class to instantiate.
    alias : str | None
        Override the component name. Takes priority over the attribute name.
    from_config : str | None
        Key to look up in the configuration file's ``presenters`` section.
    **kwargs : Any
        Additional keyword arguments forwarded to the component constructor.
    """
    return _ComponentField(
        cls=cls, layer="presenter", alias=alias, from_config=from_config, kwargs=kwargs
    )


class _ComponentBase(Generic[T]):
    """Generic base class for components."""

    __slots__ = ("cls", "name", "alias", "kwargs", "_instance")

    def __init__(
        self, cls: type[T], name: str, alias: str | None, /, **kwargs: Any
    ) -> None:
        self.cls = cls
        self.name = name
        self.alias = alias
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


class _DeviceComponent(_ComponentBase[Device]):
    """Device component wrapper."""

    def build(self) -> Device:
        """Build the device instance."""
        name = self.alias if self.alias is not None else self.name
        self._instance = self.cls(name, **self.kwargs)
        return self.instance


class _PresenterComponent(_ComponentBase[Presenter]):
    """Presenter component wrapper."""

    def build(self, name: str, devices: dict[str, Device], container: VirtualContainer) -> Presenter:
        """Build the presenter instance."""
        self._instance = self.cls(name, devices, **self.kwargs)
        return self.instance


class _ViewComponent(_ComponentBase[View]):
    """View component wrapper."""

    def build(self, name: str) -> View:
        """Build the view instance."""
        self._instance = self.cls(name, **self.kwargs)
        return self.instance
