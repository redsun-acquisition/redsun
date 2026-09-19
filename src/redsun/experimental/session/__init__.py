"""Session and component definitions for the experimental layer.

`redsun.experimental` re-exports what is here alongside the rest of the layer,
and is the import a session is written against.
"""

from __future__ import annotations

from redsun.experimental.session.components import (
    AsDevice,
    AsHook,
    AsPresenter,
    AsService,
    AsView,
)

from ._base import BUILD_STEPS, ConfigurationInUse, Session
from ._declarations import (
    Alias,
    Attach,
    Declaration,
    Declare,
    FromConfig,
    Hook,
    HookDeclaration,
    Key,
    Launch,
    Layer,
    Serves,
    accepts_name,
    check,
    read,
    read_hooks,
)
from ._factories import (
    constructor,
    defaulted,
    factory,
    injectable,
    optional_arg,
    provider,
    requirements,
    synthesize,
)
from ._frontend import Frontend
from ._plugins import PluginError, load_providers, resolve
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
    "ConfigurationInUse",
    "Declaration",
    "Declare",
    "DesktopSession",
    "FromConfig",
    "Frontend",
    "HasAsyncShutdown",
    "HasSetup",
    "HasShutdown",
    "Hook",
    "HookDeclaration",
    "Key",
    "Launch",
    "Layer",
    "NamedComponent",
    "PluginError",
    "Serializable",
    "Serves",
    "Session",
    "accepts_name",
    "check",
    "constructor",
    "defaulted",
    "factory",
    "injectable",
    "load_providers",
    "optional_arg",
    "provider",
    "read",
    "read_hooks",
    "requirements",
    "resolve",
    "synthesize",
]
