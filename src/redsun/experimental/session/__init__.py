"""Session and component definitions for the experimental layer.

`redsun.experimental` re-exports what is here alongside the rest of the layer,
and is the import a session is written against.
"""

from __future__ import annotations

from ._base import BUILD_STEPS, ConfigurationInUse, Session
from ._declarations import (
    Alias,
    Declaration,
    Declare,
    FromConfig,
    Hook,
    HookDeclaration,
    Key,
    Layer,
    Serves,
    check,
    leads_with_name,
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
from .components import AsDevice, AsHook, AsPresenter, AsView

__all__ = [
    "BUILD_STEPS",
    "Alias",
    "AsDevice",
    "AsHook",
    "AsPresenter",
    "AsView",
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
    "Layer",
    "NamedComponent",
    "PluginError",
    "Serializable",
    "Serves",
    "Session",
    "check",
    "constructor",
    "defaulted",
    "factory",
    "injectable",
    "leads_with_name",
    "load_providers",
    "optional_arg",
    "provider",
    "read",
    "read_hooks",
    "requirements",
    "resolve",
    "synthesize",
]
