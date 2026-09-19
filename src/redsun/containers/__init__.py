"""Application container and component definitions."""

from __future__ import annotations

from redsun.containers.components import (
    declare_device,
    declare_hook,
    declare_presenter,
    declare_service,
    declare_view,
)
from redsun.containers.container import AppContainer, Frontend

from ._config import AppConfig, CatalogConfig, StorageConfig
from ._hooks import HookError

__all__ = [
    "AppConfig",
    "AppContainer",
    "CatalogConfig",
    "Frontend",
    "HookError",
    "StorageConfig",
    "declare_device",
    "declare_hook",
    "declare_presenter",
    "declare_service",
    "declare_view",
]
