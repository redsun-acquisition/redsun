from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Iterable,
    TypeAlias,
    TypeVar,
)

import dependency_injector.containers as dic
import dependency_injector.providers as dip
from event_model import DocumentRouter
from event_model.documents import Document
from psygnal import Signal, SignalInstance

from redsun.log import Loggable

if TYPE_CHECKING:
    from bluesky.protocols import HasName

    from redsun.virtual._config import RedSunConfig

K = TypeVar("K")
V = TypeVar("V")

CallbackType: TypeAlias = Callable[[str, Document], None] | DocumentRouter
"""Type alias for document callback functions."""

__all__ = ["Signal", "VirtualContainer"]

SignalCache: TypeAlias = dict[str, SignalInstance]
"""Cache type for storing signal instances registered from component classes."""


@dataclass(frozen=True, kw_only=True)
class _FrozenConfig:
    """Frozen configuration dataclass."""

    schema_version: float
    frontend: str
    session: str
    metadata: dict[str, object]


class VirtualContainer(dic.DynamicContainer, Loggable):
    """Data exchange and dependency injection layer.

    `VirtualContainer` is a [`DynamicContainer`][dependency_injector.containers.DynamicContainer]
    that also acts as a runtime signal bus and data sharing layer for an application.
    """

    _signals = dip.Factory(dict[str, SignalCache])
    _callbacks = dip.Factory(dict[str, CallbackType])
    _config = dip.Singleton(_FrozenConfig)

    @property
    def schema_version(self) -> float:
        """The plugin schema version specified in the configuration."""
        return self._config().schema_version

    @property
    def frontend(self) -> str:
        """The frontend toolkit identifier specified in the configuration."""
        return self._config().frontend

    @property
    def session(self) -> str:
        """The session display name specified in the configuration."""
        return self._config().session

    @property
    def metadata(self) -> dict[str, object]:
        """The session metadata specified in the configuration."""
        return self._config().metadata

    def _set_configuration(self, config: RedSunConfig) -> None:
        """Set the application configuration.

        Private for use by the application layer at build time.

        Parameters
        ----------
        config : RedSunConfig
            The application configuration to set.
        """
        self._config.set_kwargs(
            schema_version=config["schema_version"],
            frontend=config["frontend"],
            session=config.get("session", "redsun"),
            metadata=config.get("metadata", {}),
        )

    def register_signals(
        self, owner: HasName, name: str | None = None, only: Iterable[str] | None = None
    ) -> None:
        """Register the signals of an object in the virtual container.

        Parameters
        ----------
        owner : HasName
            The instance whose class's signals are to be cached.
            Must provide a `name` attribute.
        name : str | None
            An optional name to use as the key for caching the signals.
            If not provided, the `name` of `owner` will be used.
        only : Iterable[str], optional
            A list of signal names to cache. If not provided, all
            signals in the class will be cached automatically by inspecting
            the class attributes.

        Notes
        -----
        This method inspects the attributes of the owner's class to find
        [`psygnal.Signal`][psygnal.Signal] descriptors. For each such descriptor, it
        retrieves the [`psygnal.SignalInstance`][psygnal.SignalInstance] from the owner using
        the descriptor protocol and stores it in the registry.
        """
        owner_class = type(owner)
        if name is not None:
            cache_entry = name
        else:
            cache_entry = owner.name

        if only is None:
            only = [
                name
                for name in dir(owner_class)
                if isinstance(getattr(owner_class, name, None), Signal)
            ]

        batch: dict[str, SignalInstance] = {}
        for name in only:
            signal_descriptor = getattr(owner_class, name, None)
            if isinstance(signal_descriptor, Signal):
                signal_instance = getattr(owner, name)
                batch[name] = signal_instance
        if batch:
            self._signals.add_kwargs(**{cache_entry: batch})

    @staticmethod
    def _validate_callback(callback: object) -> CallbackType:
        """Validate that *callback* is an acceptable ``CallbackType``.

        Parameters
        ----------
        callback :
            The object to validate.

        Returns
        -------
        CallbackType
            The validated callback, unchanged.

        Raises
        ------
        TypeError
            If *callback* is not callable, or if it is a callable but
            its call signature is not compatible with ``(str, Document)``.
        """
        if isinstance(callback, DocumentRouter):
            return callback

        if not callable(callback):
            raise TypeError(
                f"{callback!r} is not callable. "
                "A callback must be a DocumentRouter subclass instance or a "
                "callable accepting (str, Document) arguments."
            )

        try:
            inspect.signature(callback.__call__).bind(None, None)
        except TypeError as e:
            raise TypeError(
                f"{callback!r} is callable but its signature is not compatible "
                "with the expected (str, Document) callback interface."
            ) from e

        return callback

    def register_callbacks(
        self,
        owner: HasName,
        name: str | None = None,
        callback_map: dict[str, CallbackType] | None = None,
    ) -> None:
        """Register one or more document callbacks in the virtual container.

        Accepts any object that is a valid ``CallbackType`` and exposes a
        ``name`` attribute used as the registry key.  Two forms are supported:

        * A [DocumentRouter][event_model.DocumentRouter] subclass instance;
        * Any other object that implements ``__call__(self, name, doc)`` with
          the correct two-parameter signature.

        When *callback_map* is provided the owner itself is not registered;
        instead each entry in the mapping is validated and registered
        independently under its own key, allowing a single owner to expose
        multiple callbacks.

        Parameters
        ----------
        owner : HasName
            The component registering callbacks.  Must expose a ``name``
            attribute.  When *callback_map* is ``None``, *owner* itself is
            registered as the callback.
        name : str | None
            Override for the registry key used when registering *owner*
            directly.  Ignored when *callback_map* is provided.
            Defaults to ``owner.name``.
        callback_map : dict[str, CallbackType] | None
            Optional mapping of registry key to callback object.  When
            supplied, each value is validated and registered under its
            corresponding key; *name* is ignored.

        Raises
        ------
        TypeError
            If a callback is not callable or its signature is incompatible
            with ``(str, Document)``.
        """
        if callback_map is not None:
            for key, callback in callback_map.items():
                self._callbacks.add_kwargs(**{key: self._validate_callback(callback)})
            return

        cache_entry = name if name is not None else owner.name
        self._callbacks.add_kwargs(**{cache_entry: self._validate_callback(owner)})

    @property
    def callbacks(self) -> dict[str, CallbackType]:
        """The currently registered document callbacks."""
        return self._callbacks()

    @property
    def signals(self) -> dict[str, SignalCache]:
        """The currently registered signals."""
        return self._signals()
