from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Literal, TypedDict, TypeVar, overload

from sunflare.device import Device
from sunflare.presenter import Presenter
from sunflare.view import View
from typing_extensions import NotRequired, Required

if TYPE_CHECKING:
    from sunflare.virtual import VirtualBus


T = TypeVar("T")


class RedSunConfig(TypedDict, total=False):
    """Base configuration dictionary for Redsun containers.

    Describes the common top-level keys that may appear in a container
    configuration YAML file.  Users should inherit from this class to
    add component-specific sections.
    """

    schema: Required[float]
    """Version number for the configuration schema."""
    session: Required[str]
    """Display name for the session."""
    frontend: Required[str]
    """Frontend toolkit identifier (e.g. ``"pyqt"``, ``"pyside"``)."""

    devices: NotRequired[dict[str, Any]]
    """Dictionary of device kwargs, keyed by component name."""
    presenters: NotRequired[dict[str, Any]]
    """Dictionary of presenter kwargs, keyed by component name."""
    views: NotRequired[dict[str, Any]]
    """Dictionary of view kwargs, keyed by component name."""


class _ConfigField:
    """Internal sentinel returned by `config`.

    Stores the path to a YAML configuration file.  The
    `AppContainerMeta` metaclass loads the file and makes its
    contents available to `component` fields that set
    ``from_config=True``.
    """

    __slots__ = ("path",)

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)


def config(path: str | Path) -> Any:
    """Declare a container-level configuration file.

    The type annotation on the attribute should be a `TypedDict`
    subclass of `RedSunConfig` describing the expected shape of the
    YAML file.  At class creation time the file is loaded and its
    sections are used to populate kwargs for any `component` field
    that sets ``from_config=True``.

    Parameters
    ----------
    path : ``str | Path``
        Path to a YAML configuration file.

    Returns
    -------
    ``Any``
        A `_ConfigField` sentinel.

    Examples
    --------
    >>> class MotorKwargs(TypedDict):
    ...     axis: list[str]
    ...     step_size: dict[str, float]
    >>> class AppConfig(RedSunConfig):
    ...     motor: MotorKwargs
    >>> class MyApp(AppContainer):
    ...     cfg: AppConfig = config("app_config.yaml")
    ...     motor: MyMotor = component(layer="model", from_config=True)
    """
    return _ConfigField(path=path)


class _ComponentField:
    """Internal sentinel returned by `component`.

    Stores the layer assignment and keyword arguments until the
    `AppContainerMeta` metaclass resolves them into concrete
    component wrappers.
    """

    __slots__ = ("layer", "alias", "from_config", "kwargs")

    def __init__(
        self,
        layer: Literal["model", "presenter", "view"],
        alias: str | None,
        from_config: bool,
        kwargs: dict[str, Any],
    ) -> None:
        self.layer = layer
        self.alias = alias
        self.from_config = from_config
        self.kwargs = kwargs


@overload
def component(
    *,
    layer: Literal["model"],
    alias: str | None = ...,
    from_config: Literal[True] = ...,
    **kwargs: Any,
) -> Any: ...
@overload
def component(
    *,
    layer: Literal["model"],
    alias: str | None = ...,
    from_config: Literal[False] = ...,
    **kwargs: Any,
) -> Any: ...
@overload
def component(
    *,
    layer: Literal["presenter"],
    alias: str | None = ...,
    from_config: Literal[True] = ...,
    **kwargs: Any,
) -> Any: ...
@overload
def component(
    *,
    layer: Literal["presenter"],
    alias: str | None = ...,
    from_config: Literal[False] = ...,
    **kwargs: Any,
) -> Any: ...
@overload
def component(
    *,
    layer: Literal["view"],
    alias: str | None = ...,
    from_config: Literal[True] = ...,
    **kwargs: Any,
) -> Any: ...
@overload
def component(
    *,
    layer: Literal["view"],
    alias: str | None = ...,
    from_config: Literal[False] = ...,
    **kwargs: Any,
) -> Any: ...
def component(
    *,
    layer: Literal["model", "presenter", "view"],
    alias: str | None = None,
    from_config: bool = False,
    **kwargs: Any,
) -> Any:
    """Declare a component as a class field.

    This function is a field specifier for use with
    `~redsun.containers.AppContainer` subclasses.  The type
    annotation on the attribute provides the component class, and the
    attribute name becomes the component name.

    Parameters
    ----------
    layer : "model" | "presenter" | "view"
        The layer this component belongs to.
    from_config : bool
        If `True`, the component's kwargs are loaded from the
        container-level `config` field at class creation time.
        The component's attribute name is used as the lookup key in the
        loaded configuration dictionary.  Inline ``**kwargs`` override
        values from the config file.
    **kwargs : `Any`
        Additional keyword arguments forwarded to the component
        constructor at build time.

    Returns
    -------
    `Any`
        A `_ComponentField` sentinel (typed as `Any` so that
        `attr: MyClass = component(...)` satisfies type checkers).

    Examples
    --------
    >>> class MyApp(AppContainer):
    ...     motor: MyMotor = component(layer="model", axis=["X"])
    ...     ctrl: MyCtrl = component(layer="presenter", gain=1.0)
    ...     ui: MyView = component(layer="view")

    With a config file:

    >>> class MyApp(AppContainer):
    ...     cfg: AppConfig = config("app_config.yaml")
    ...     motor: MyMotor = component(layer="model", from_config=True)
    """
    return _ComponentField(
        layer=layer, alias=alias, from_config=from_config, kwargs=kwargs
    )


class _ComponentBase(Generic[T]):
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


class _DeviceComponent(_ComponentBase[Device]):
    """Device component wrapper."""

    def build(self) -> Device:
        """Build the device instance."""
        self._instance = self.cls(self.name, **self.kwargs)
        return self.instance


class _PresenterComponent(_ComponentBase[Presenter]):
    """Presenter component wrapper."""

    def build(self, devices: dict[str, Device], virtual_bus: VirtualBus) -> Presenter:
        """Build the presenter instance."""
        self._instance = self.cls(devices, virtual_bus, **self.kwargs)
        return self.instance


class _ViewComponent(_ComponentBase[View]):
    """View component wrapper."""

    def build(self, virtual_bus: VirtualBus) -> View:
        """Build the view instance."""
        self._instance = self.cls(virtual_bus, **self.kwargs)
        return self.instance
