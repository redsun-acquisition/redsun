from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from sunflare.device import Device
from sunflare.presenter import Presenter
from sunflare.view import View

if TYPE_CHECKING:
    from sunflare.virtual import VirtualContainer


T = TypeVar("T")


class _DeviceField:
    """Sentinel returned by :func:`device`. Resolved by the metaclass into a ``_DeviceComponent``."""

    __slots__ = ("cls", "alias", "from_config", "kwargs")

    def __init__(self, cls: type, alias: str | None, from_config: str | None, kwargs: dict[str, Any]) -> None:
        self.cls = cls
        self.alias = alias
        self.from_config = from_config
        self.kwargs = kwargs


class _PresenterField:
    """Sentinel returned by :func:`presenter`. Resolved by the metaclass into a ``_PresenterComponent``."""

    __slots__ = ("cls", "alias", "from_config", "kwargs")

    def __init__(self, cls: type, alias: str | None, from_config: str | None, kwargs: dict[str, Any]) -> None:
        self.cls = cls
        self.alias = alias
        self.from_config = from_config
        self.kwargs = kwargs


class _ViewField:
    """Sentinel returned by :func:`view`. Resolved by the metaclass into a ``_ViewComponent``."""

    __slots__ = ("cls", "alias", "from_config", "kwargs")

    def __init__(self, cls: type, alias: str | None, from_config: str | None, kwargs: dict[str, Any]) -> None:
        self.cls = cls
        self.alias = alias
        self.from_config = from_config
        self.kwargs = kwargs


# Union used for isinstance checks in the metaclass.
_AnyField = _DeviceField | _PresenterField | _ViewField


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
    container is built. The attribute name ``motor`` will be used as the device ``name`` argument.

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
    return _DeviceField(cls=cls, alias=alias, from_config=from_config, kwargs=kwargs)


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
    return _ViewField(cls=cls, alias=alias, from_config=from_config, kwargs=kwargs)


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
    return _PresenterField(cls=cls, alias=alias, from_config=from_config, kwargs=kwargs)


class _ComponentBase(Generic[T]):
    """Generic base class for components.

    The ``name`` attribute holds the fully-resolved component name.
    For declarative fields it is ``alias`` (if set) or the attribute name;
    for ``from_config()``-built containers it is the YAML key.
    """

    __slots__ = ("cls", "name", "kwargs", "_instance")

    def __init__(self, cls: type[T], name: str, /, **kwargs: Any) -> None:
        self.cls = cls
        self.name = name
        self.kwargs = kwargs
        self._instance: T | None = None

    @property
    def instance(self) -> T:
        """Return the built instance, raising ``RuntimeError`` if not yet built."""
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
        self._instance = self.cls(self.name, **self.kwargs)
        return self.instance


class _PresenterComponent(_ComponentBase[Presenter]):
    """Presenter component wrapper."""

    def build(self, devices: dict[str, Device], container: VirtualContainer) -> Presenter:
        """Build the presenter instance."""
        self._instance = self.cls(self.name, devices, **self.kwargs)
        return self.instance


class _ViewComponent(_ComponentBase[View]):
    """View component wrapper."""

    def build(self) -> View:
        """Build the view instance."""
        self._instance = self.cls(self.name, **self.kwargs)
        return self.instance
