from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator, Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeAlias

from event_model import DocumentRouter
from event_model.documents import Document
from ophyd_async.core import Device

from redsun.experimental.virtual._wiring import (
    SessionNotBuilt,
)

if TYPE_CHECKING:
    from bluesky.protocols import HasName


__all__ = [
    "BlueskyCallbackRegistry",
    "CallbackType",
    "DeviceMapping",
    "SessionConfig",
]

# these three are dependency keys, so every name in them must resolve at runtime:
# the graph evaluates the annotation, and a TYPE_CHECKING-only import fails there
CallbackType: TypeAlias = Callable[[str, Document], None] | DocumentRouter
"""A document callback: a `DocumentRouter`, or anything callable as ``(name, doc)``."""

DeviceMapping: TypeAlias = Mapping[str, Device]
"""Every device an application built, by name.

Not ophyd-async's ``DeviceMap``, which is a device holding string-keyed
children; this is the application's own set.
"""

"""The signals one component declares, by attribute name."""


def validate_callback(callback: object) -> CallbackType:
    """Return *callback* unchanged if it can be called as ``(name, doc)``.

    Raises
    ------
    TypeError
        If *callback* is not callable, or its signature is incompatible
        with ``(str, Document)``.
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


class BlueskyCallbackRegistry(Mapping[str, CallbackType]):
    """The bluesky document-callback registry, as a component sees it.

    A component receives this while it is being built. It may register its own
    callbacks straight away, and it may hold the mapping and read it when it
    runs. Reading it before the application has finished building raises,
    because the components after it have registered nothing yet and the answer
    would be incomplete.

    Parameters
    ----------
    registry : MutableMapping[str, CallbackType]
        The mapping every component registers into, held rather than copied so
        that a component reads what later ones added.
    ready : Callable[[], bool]
        Answers whether every component has been built. Reading the mapping
        before it answers ``True`` raises.

    Raises
    ------
    LookupError
        If read before every component exists.
    """

    def __init__(
        self, registry: MutableMapping[str, CallbackType], ready: Callable[[], bool]
    ) -> None:
        self._registry = registry
        self._ready = ready

    def register(
        self,
        owner: HasName,
        *,
        name: str | None = None,
        callback_map: dict[str, CallbackType] | None = None,
    ) -> None:
        """Register one or more document callbacks.

        Parameters
        ----------
        owner : HasName
            The component registering callbacks, and the callback itself when
            *callback_map* is ``None``.
        name : str | None
            Registry key for *owner*. Defaults to ``owner.name``; ignored when
            *callback_map* is given.
        callback_map : dict[str, CallbackType] | None
            Several callbacks from one owner, each registered under its own
            key. *owner* is then not registered itself.

        Raises
        ------
        TypeError
            If a callback is not callable or its signature is incompatible
            with ``(str, Document)``.
        """
        if callback_map is not None:
            for key, callback in callback_map.items():
                self._registry[key] = validate_callback(callback)
            return

        self._registry[name if name is not None else owner.name] = validate_callback(
            owner
        )

    def _complete(self) -> Mapping[str, CallbackType]:
        if not self._ready():
            raise SessionNotBuilt(
                "the document-callback registry is not complete until every "
                "component exists. Hold this view and read it when the "
                "component runs, rather than copying it while it is built."
            )
        return self._registry

    def __getitem__(self, key: str) -> CallbackType:
        return self._complete()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._complete())

    def __len__(self) -> int:
        return len(self._complete())

    def __repr__(self) -> str:
        state = "live" if self._ready() else "pending"
        return f"BlueskyCallbackRegistry({state}, {len(self._registry)} registered)"


@dataclass(frozen=True, kw_only=True)
class SessionConfig:
    """The configuration an application was built from."""

    schema_version: float = 1.0
    frontend: str = "pyqt"
    name: str = "Redsun"
    metadata: dict[str, object] = field(default_factory=dict)
