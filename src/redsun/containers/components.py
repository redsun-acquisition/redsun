"""Component field definitions."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast, overload

from ophyd_async.core import Device

from redsun.presenter import PPresenter
from redsun.view import PView

from ._structural import problems

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")


def expects_positionals(cls: Callable[..., Any], expected: tuple[str, ...]) -> bool:
    """Verify a component constructor's positional shape.

    The container instantiates components as ``cls(*positionals, **kwargs)``
    with *kwargs* coming from the configuration file, so the class-level
    contract is purely positional: the constructor's leading positional
    parameters must be exactly *expected* (checked by name and by binding),
    any further positional-or-keyword parameters must carry defaults, and
    ``*args`` is rejected. Keyword arguments are deliberately not validated - the container has no control over them.

    Parameters
    ----------
    cls : Callable[..., Any]
        The component class (or factory) to inspect.
    expected : tuple[str, ...]
        The exact names of the leading positional parameters, in order
        (e.g. ``("name", "devices")`` for presenters, ``("name",)`` for
        views).
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
    """Declare a component as a device layer field.

    A device can be declared inside the body of an `AppContainer`:

    ```python
    class MyApp(AppContainer):
        motor = declare_device(MyMotor, axis=["X"])
    ```

    The attribute is typed as *cls*, so reading it on a built container gives a
    checked `MyMotor`.

    Parameters
    ----------
    cls : type[T]
        The component class to instantiate.
    alias : str | None
        Component name, overriding the attribute name.
    from_config : str | None
        Key to read further keyword arguments from, in the configuration
        file's ``devices`` section. Read from the file the container class
        naming the field declares, so a subclass with a ``config`` of its own
        reads this field from that file.
    **kwargs : Any
        Keyword arguments forwarded to the component constructor.
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
    """Declare a component as a view layer field.

    ```python
    class MyApp(AppContainer):
        ui = declare_view(MyView)
    ```

    The attribute is typed as *cls*, so reading it on a built container gives a
    checked `MyView`.

    Parameters
    ----------
    cls : type[T]
        The component class to instantiate.
    alias : str | None
        Component name, overriding the attribute name.
    from_config : str | None
        Key to read further keyword arguments from, in the configuration
        file's ``views`` section. Read from the file the container class
        naming the field declares, so a subclass with a ``config`` of its own
        reads this field from that file.
    **kwargs : Any
        Keyword arguments forwarded to the component constructor.
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
    """Declare a component as a presenter layer field.

    ```python
    class MyApp(AppContainer):
        ctrl = declare_presenter(MyCtrl, gain=1.0)
    ```

    The attribute is typed as *cls*, so a connection written in
    [`wire`][redsun.containers.container.AppContainer.wire] is checked: naming a
    signal or slot the class does not have is an error before the build runs.

    Parameters
    ----------
    cls : type[T]
        The component class to instantiate.
    alias : str | None
        Component name, overriding the attribute name.
    from_config : str | None
        Key to read further keyword arguments from, in the configuration
        file's ``presenters`` section. Read from the file the container class
        naming the field declares, so a subclass with a ``config`` of its own
        reads this field from that file.
    **kwargs : Any
        Keyword arguments forwarded to the component constructor.
    """
    return cast(
        "T",
        _PresenterField(cls=cls, alias=alias, from_config=from_config, kwargs=kwargs),
    )


class _ComponentBase(Generic[T]):
    """Generic base class for components.

    The ``name`` attribute holds the fully-resolved component name.
    For declarative fields it is ``alias`` (if set) or the attribute name;
    for ``from_config()``-built containers it is the YAML key.
    """

    __slots__ = ("_instance", "cls", "kwargs", "name")

    def __init__(self, cls: Callable[..., T], name: str, /, **kwargs: Any) -> None:
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

    def __get__(self, obj: object, objtype: type | None = None) -> Any:
        """Resolve to the built instance when read from a container instance.

        Reading the attribute on the class, or before the component is built,
        gives the wrapper itself.
        """
        if obj is None or self._instance is None:
            return self
        return self._instance

    def __repr__(self) -> str:
        status = "built" if self._instance is not None else "pending"
        return f"{self.__class__.__name__}({self.name!r}, {status})"


class _DeviceComponent(_ComponentBase[Device]):
    """Device component wrapper."""

    def build(self) -> Device:
        """Build the device instance, validating it is an ophyd-async Device."""
        instance = self.cls(self.name, **self.kwargs)
        if not isinstance(instance, Device):
            raise TypeError(
                f"{type(instance).__name__!r} (device {self.name!r}) is not an "
                "ophyd-async Device."
            )
        self._instance = instance
        return instance


class _PresenterComponent(_ComponentBase[PPresenter]):
    """Presenter component wrapper.

    Validation is a dual gate: the constructor's positional shape
    (``name``, ``devices``) is checked at wrapper creation via
    ``inspect``; PPresenter compliance is validated on the built
    instance - class-level checks cannot see attributes assigned in
    ``__init__``.
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
        """Build the presenter instance, validating the PPresenter protocol."""
        instance = self.cls(self.name, devices, **self.kwargs)
        if not isinstance(instance, PPresenter):
            raise TypeError(
                f"{type(instance).__name__!r} (presenter {self.name!r}) does not "
                "implement the PPresenter protocol: "
                + "; ".join(problems(instance, PPresenter))
            )
        self._instance = instance
        return instance


class _ViewComponent(_ComponentBase[PView]):
    """View component wrapper.

    Validation is a dual gate: the constructor's positional shape
    (``name``) is checked at wrapper creation via ``inspect``; PView
    compliance is validated on the built instance - class-level checks
    cannot see attributes assigned in ``__init__``.
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
        """Build the view instance, validating the PView protocol."""
        instance = self.cls(self.name, **self.kwargs)
        if not isinstance(instance, PView):
            raise TypeError(
                f"{type(instance).__name__!r} (view {self.name!r}) does not "
                "implement the PView protocol: " + "; ".join(problems(instance, PView))
            )
        self._instance = instance
        return instance


__all__ = ["declare_device", "declare_presenter", "declare_view"]


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

    The attribute name is the method the hook point calls, so a container
    installs at most one provider per point:

    ```python
    class MyApp(QtAppContainer):
        configure_application = declare_hook(DarkTheme, theme="nord")
    ```

    A class is constructed with *kwargs* as the container class is created; an
    already built instance is taken as it is, and the same instance declared at
    two points is one provider serving both.

    Parameters
    ----------
    provider : type[T] | T
        The provider class to instantiate, or a provider already built.
    **kwargs : Any
        Keyword arguments forwarded to the provider constructor.

    Raises
    ------
    TypeError
        If keyword arguments are given for a provider that is already built.
    """
    if not isinstance(provider, type) and kwargs:
        raise TypeError(
            f"declare_hook takes keyword arguments only with a class; "
            f"{type(provider).__name__} is already constructed"
        )
    return _HookField(provider=provider, kwargs=kwargs)
