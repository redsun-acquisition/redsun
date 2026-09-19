"""The ``declare_*`` functions and the component wrappers they create."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast, overload

from ophyd_async.core import Device

from redsun._structural import problems
from redsun.presenter import PPresenter
from redsun.services import STOP_TIMEOUT, Service
from redsun.view import PView

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from ophyd_async.core import PathProvider

    from redsun.containers.container import AppContainer

T = TypeVar("T")


def expects_positionals(cls: Callable[..., Any], expected: tuple[str, ...]) -> bool:
    """Verify a component constructor's positional shape.

    The container calls ``cls(*positionals, **kwargs)`` with *kwargs* from the
    configuration file, so only the positional shape is checked: the leading
    positional parameters must be exactly *expected*, by name and by binding,
    any further positional-or-keyword parameter needs a default, and ``*args``
    is refused. Keyword arguments are not checked, since the configuration
    supplies them.

    Parameters
    ----------
    cls : Callable[..., Any]
        The component class or factory.
    expected : tuple[str, ...]
        Names of the leading positional parameters, in order:
        ``("name", "devices")`` for presenters, ``("name",)`` for views.
    """
    try:
        sig = inspect.signature(cls)
    except (TypeError, ValueError):
        return False
    parameters = list(sig.parameters.values())
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in parameters):
        return False
    positionals = [
        p
        for p in parameters
        if p.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positionals) < len(expected):
        return False
    if tuple(p.name for p in positionals[: len(expected)]) != expected:
        return False
    if any(p.default is inspect.Parameter.empty for p in positionals[len(expected) :]):
        return False
    try:
        # per-contract check: the container's positional call must bind
        sig.bind_partial(*(object() for _ in expected))
    except TypeError:
        return False
    return True


class _ComponentField:
    """Base sentinel a ``declare_*`` call returns, resolved by the metaclass."""

    __slots__ = ("alias", "cls", "from_config", "kwargs")

    def __init__(
        self,
        cls: type,
        alias: str | None,
        from_config: str | None,
        kwargs: dict[str, Any],
    ) -> None:
        self.cls = cls
        self.alias = alias
        self.from_config = from_config
        self.kwargs = kwargs


class _DeviceField(_ComponentField):
    """Sentinel returned by [`declare_device`][redsun.containers.declare_device]. Resolved by the metaclass into a ``_DeviceComponent``."""

    __slots__ = ()


class _PresenterField(_ComponentField):
    """Sentinel returned by [`declare_presenter`][redsun.containers.declare_presenter]. Resolved by the metaclass into a ``_PresenterComponent``."""

    __slots__ = ()


class _ViewField(_ComponentField):
    """Sentinel returned by [`declare_view`][redsun.containers.declare_view]. Resolved by the metaclass into a ``_ViewComponent``."""

    __slots__ = ()


def declare_device(
    cls: type[T],
    /,
    alias: str | None = None,
    from_config: str | None = None,
    **kwargs: Any,
) -> T:
    """Declare a device on a container.

    ```python
    class MyApp(AppContainer):
        motor = declare_device(MyMotor, axis=["X"])
    ```

    The attribute's type is *cls*, so on a built container it is a `MyMotor`.

    Parameters
    ----------
    cls : type[T]
        The component class to instantiate.
    alias : str | None
        Component name, overriding the attribute name.
    from_config : str | None
        Key in the configuration file's ``devices`` section holding more
        keyword arguments. The file is the one declared by the container class
        using the field, so a subclass with its own ``config`` reads its own.
    **kwargs : Any
        Keyword arguments passed to the constructor.
    """
    return cast(
        "T", _DeviceField(cls=cls, alias=alias, from_config=from_config, kwargs=kwargs)
    )


def declare_view(
    cls: type[T],
    /,
    alias: str | None = None,
    from_config: str | None = None,
    **kwargs: Any,
) -> T:
    """Declare a view on a container.

    ```python
    class MyApp(AppContainer):
        ui = declare_view(MyView)
    ```

    The attribute's type is *cls*, so on a built container it is a `MyView`.

    Parameters
    ----------
    cls : type[T]
        The component class to instantiate.
    alias : str | None
        Component name, overriding the attribute name.
    from_config : str | None
        Key in the configuration file's ``views`` section holding more keyword
        arguments. The file is the one declared by the container class using
        the field, so a subclass with its own ``config`` reads its own.
    **kwargs : Any
        Keyword arguments passed to the constructor.
    """
    return cast(
        "T", _ViewField(cls=cls, alias=alias, from_config=from_config, kwargs=kwargs)
    )


def declare_presenter(
    cls: type[T],
    /,
    alias: str | None = None,
    from_config: str | None = None,
    **kwargs: Any,
) -> T:
    """Declare a presenter on a container.

    ```python
    class MyApp(AppContainer):
        ctrl = declare_presenter(MyCtrl, gain=1.0)
    ```

    The attribute's type is *cls*, so connections in
    [`wire`][redsun.containers.container.AppContainer.wire] are type-checked:
    naming a signal or slot the class lacks is an error before the build.

    Parameters
    ----------
    cls : type[T]
        The component class to instantiate.
    alias : str | None
        Component name, overriding the attribute name.
    from_config : str | None
        Key in the configuration file's ``presenters`` section holding more
        keyword arguments. The file is the one declared by the container class
        using the field, so a subclass with its own ``config`` reads its own.
    **kwargs : Any
        Keyword arguments passed to the constructor.
    """
    return cast(
        "T",
        _PresenterField(cls=cls, alias=alias, from_config=from_config, kwargs=kwargs),
    )


def declare_service(
    *,
    module: str | None = None,
    ready: str | None = None,
    prefix: str = "",
    args: Sequence[str] = (),
    stop_timeout: float = STOP_TIMEOUT,
    alias: str | None = None,
) -> Service:
    """Declare a service the container's devices talk to.

    A service with a *module* is launched as ``python -m <module> <args>`` when
    the container is built; one without is attached to, already running
    elsewhere:

    ```python
    class MyApp(AppContainer):
        camera_ioc = declare_service(
            module="mylab.iocs.camera", ready="Server startup complete.", prefix="CAM:"
        )
        camera = declare_device(MyCamera, service="camera_ioc")
    ```

    A device naming the service receives its prefix as ``prefix``. The
    attribute's type is `redsun.services.Service`, so ``wire`` can connect its
    ``sig_exited``.

    Parameters
    ----------
    module : str | None
        Module to run. ``None`` attaches to a service that is already running.
    ready : str | None
        Text of the output line marking a launched service ready. ``None``
        counts it ready once its process starts.
    prefix : str
        Prefix given to each device naming the service.
    args : Sequence[str]
        Command-line arguments following the module.
    stop_timeout : float
        Seconds each stopping step waits for the service to exit.
    alias : str | None
        Service name, overriding the attribute name.
    """
    kwargs: dict[str, Any] = {
        "module": module,
        "ready": ready,
        "prefix": prefix,
        "args": args,
        "stop_timeout": stop_timeout,
    }
    return cast("Service", _ServiceComponent(alias or "", **kwargs))


class _ServiceComponent:
    """A declared service, from which each container makes a `Service` of its own.

    Without a name, it takes the attribute name it is assigned to.
    """

    __slots__ = ("kwargs", "name")

    def __init__(self, name: str = "", /, **kwargs: Any) -> None:
        self.name = name
        self.kwargs = kwargs

    def __set_name__(self, owner: type, attr: str) -> None:
        self.name = self.name or attr

    def create(self) -> Service:
        """Return a new `Service` for this declaration."""
        return Service(self.name, **self.kwargs)

    def __get__(self, obj: object, objtype: type | None = None) -> Any:
        """Resolve to the container's own `Service` when read from a container."""
        if obj is None:
            return self
        return cast("AppContainer", obj)._services[self.name]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name!r})"


class _NotBuilt:
    """Stands in for a component the build failed on.

    Any attribute read gives another one carrying the name read, so ``wire``
    naming a missing component reaches ``connect`` instead of raising, and the
    other connections are still made.
    """

    __slots__ = ("component", "port")

    def __init__(self, component: str, port: str = "") -> None:
        self.component = component
        self.port = port

    def __getattr__(self, name: str) -> _NotBuilt:
        # a dunder answered with a stand-in would make this object claim
        # protocols it does not implement, copy and pickle among them
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _NotBuilt(self.component, name)

    def __str__(self) -> str:
        return f"{self.component}.{self.port}" if self.port else self.component

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self!s})"


class _ComponentBase(Generic[T]):
    """Generic base class for components.

    ``name`` is the resolved component name: ``alias`` or the attribute name
    when declared in Python, the YAML key for a ``from_config()`` container.

    A wrapper is a declaration and holds no built object. Each container keeps
    what it built, keyed by the wrapper, so two containers of one class build
    their own components, and none outlives its container.
    """

    __slots__ = ("cls", "kwargs", "name")

    def __init__(self, cls: Callable[..., T], name: str, /, **kwargs: Any) -> None:
        self.cls = cls
        self.name = name
        self.kwargs = kwargs

    def __get__(self, obj: object, objtype: type | None = None) -> Any:
        """Resolve to the built instance when read from a built container.

        On the class, or on a container not built or shut down, it gives the
        wrapper. A component that failed to build gives a `_NotBuilt` until
        shutdown.
        """
        if obj is None:
            return self
        container = cast("AppContainer", obj)
        if self in container._built:
            return container._built[self]
        if self.name in container._failed:
            return _NotBuilt(self.name)
        return self

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name!r})"


class _DeviceComponent(_ComponentBase[Device]):
    """Device component wrapper.

    The container keeps two keywords from the constructor: ``service``, naming
    the service whose prefix the device gets, and ``autoconnect``, true unless
    given, whether the build connects it. ``path_provider`` is reserved too:
    a device taking one gets the session's, so a declaration cannot give it.
    """

    __slots__ = ("autoconnect", "service")

    def __init__(self, cls: Callable[..., Device], name: str, /, **kwargs: Any) -> None:
        for reserved in ("service", "autoconnect", "path_provider"):
            if reserved in kwargs and _takes_keyword(cls, reserved):
                raise TypeError(
                    f"{cls!r} (device {name!r}) takes a {reserved!r} keyword of "
                    "its own, which a device declaration reserves for the container"
                )
        service: str | None = kwargs.pop("service", None)
        if service is not None and "prefix" in kwargs:
            raise TypeError(
                f"device {name!r} names service {service!r} and a prefix; "
                "give one, the service's prefix is the device's"
            )
        autoconnect = kwargs.pop("autoconnect", True)
        if not isinstance(autoconnect, bool):
            raise TypeError(
                f"device {name!r} gives autoconnect={autoconnect!r}; "
                "it takes true or false"
            )
        super().__init__(cls, name, **kwargs)
        self.service = service
        self.autoconnect = autoconnect

    def build(
        self, prefix: str | None = None, path_provider: PathProvider | None = None
    ) -> Device:
        """Build the device, checking it is an ``ophyd-async`` Device.

        *prefix*, the one the device's service gives, is passed as ``prefix``.
        *path_provider*, the session's, is passed as ``path_provider`` to a
        device whose constructor takes that keyword, and withheld from one
        that does not.
        """
        extra: dict[str, Any] = {} if prefix is None else {"prefix": prefix}
        if path_provider is not None and _takes_keyword(self.cls, "path_provider"):
            extra["path_provider"] = path_provider
        instance = self.cls(name=self.name, **self.kwargs, **extra)
        if not isinstance(instance, Device):
            raise TypeError(
                f"{type(instance).__name__!r} (device {self.name!r}) is not an "
                "ophyd-async Device."
            )
        return instance


class _PresenterComponent(_ComponentBase[PPresenter]):
    """Presenter component wrapper.

    Checked twice: the constructor's positional shape (``name``, ``devices``)
    when the wrapper is created, and the PPresenter protocol on the built
    instance, since attributes assigned in ``__init__`` are not on the class.
    """

    def __init__(
        self, cls: Callable[..., PPresenter], name: str, /, **kwargs: Any
    ) -> None:
        if not expects_positionals(cls, ("name", "devices")):
            raise TypeError(
                f"{cls!r} (presenter {name!r}) must accept exactly "
                "('name', 'devices') as its leading positional parameters; "
                "any further parameters must be keyword-assignable."
            )
        super().__init__(cls, name, **kwargs)

    def build(self, devices: dict[str, Device]) -> PPresenter:
        """Build the presenter, checking the PPresenter protocol."""
        instance = self.cls(self.name, devices, **self.kwargs)
        if not isinstance(instance, PPresenter):
            raise TypeError(
                f"{type(instance).__name__!r} (presenter {self.name!r}) does not "
                "implement the PPresenter protocol: "
                + "; ".join(problems(instance, PPresenter))
            )
        return instance


class _ViewComponent(_ComponentBase[PView]):
    """View component wrapper.

    Checked twice: the constructor's positional shape (``name``) when the
    wrapper is created, and the PView protocol on the built instance, since
    attributes assigned in ``__init__`` are not on the class.
    """

    def __init__(self, cls: Callable[..., PView], name: str, /, **kwargs: Any) -> None:
        if not expects_positionals(cls, ("name",)):
            raise TypeError(
                f"{cls!r} (view {name!r}) must accept exactly ('name',) as "
                "its leading positional parameter; any further parameters "
                "must be keyword-assignable."
            )
        super().__init__(cls, name, **kwargs)

    def build(self) -> PView:
        """Build the view, checking the PView protocol."""
        instance = self.cls(self.name, **self.kwargs)
        if not isinstance(instance, PView):
            raise TypeError(
                f"{type(instance).__name__!r} (view {self.name!r}) does not "
                "implement the PView protocol: " + "; ".join(problems(instance, PView))
            )
        return instance


def _takes_keyword(cls: Callable[..., Any], keyword: str) -> bool:
    """Return whether *cls* names a parameter *keyword* that a caller may pass."""
    try:
        parameter = inspect.signature(cls).parameters.get(keyword)
    except (TypeError, ValueError):
        return False
    return parameter is not None and parameter.kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    )


__all__ = ["declare_device", "declare_presenter", "declare_service", "declare_view"]


class _HookField:
    """Sentinel returned by [`declare_hook`][redsun.containers.declare_hook]. Resolved by the metaclass into a provider instance."""

    __slots__ = ("kwargs", "provider")

    def __init__(self, provider: Any, kwargs: dict[str, Any]) -> None:
        self.provider = provider
        self.kwargs = kwargs


@overload
def declare_hook(provider: type[T], /, **kwargs: Any) -> T: ...
@overload
def declare_hook(provider: T, /) -> T: ...
def declare_hook(provider: Any, /, **kwargs: Any) -> Any:
    """Declare a hook provider for the hook point the attribute names.

    The attribute name is the method the hook point calls, so a container has
    at most one provider per point:

    ```python
    class MyApp(QtAppContainer):
        configure_application = declare_hook(DarkTheme, theme="nord")
    ```

    A class is constructed with *kwargs* when the container class is created;
    an instance is used as is, and one instance declared at two points serves
    both.

    Parameters
    ----------
    provider : type[T] | T
        The provider class to instantiate, or a provider already built.
    **kwargs : Any
        Keyword arguments passed to the provider's constructor.

    Raises
    ------
    TypeError
        If keyword arguments are given with an instance.
    """
    if not isinstance(provider, type) and kwargs:
        raise TypeError(
            f"declare_hook takes keyword arguments only with a class; "
            f"{type(provider).__name__} is already constructed"
        )
    return _HookField(provider=provider, kwargs=kwargs)
