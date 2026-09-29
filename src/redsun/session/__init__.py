"""Session and component definitions.

`redsun` re-exports what is here alongside the rest of the layer,
and is the import a session is written against.
"""

from __future__ import annotations

from redsun.session.components import (
    AsDevice,
    AsHook,
    AsPresenter,
    AsService,
    AsView,
)

from ._base import BUILD_STEPS, Session
from ._declarations import (
    Alias,
    Attach,
    Declaration,
    Declare,
    FromConfig,
    Launch,
    Layer,
    Serves,
)
from ._frontend import Frontend
from ._protocols import (
    AttachableComponent,
    BuildableSession,
    DesktopSession,
    HasAsyncShutdown,
    HasSetup,
    HasShutdown,
    NamedComponent,
    Serializable,
)

__all__ = [
    "BUILD_STEPS",
    "Alias",
    "AsDevice",
    "AsHook",
    "AsPresenter",
    "AsService",
    "AsView",
    "Attach",
    "AttachableComponent",
    "BuildableSession",
    "Declaration",
    "Declare",
    "DesktopSession",
    "FromConfig",
    "Frontend",
    "HasAsyncShutdown",
    "HasSetup",
    "HasShutdown",
    "Launch",
    "Layer",
    "NamedComponent",
    "Serializable",
    "Serves",
    "Session",
]
