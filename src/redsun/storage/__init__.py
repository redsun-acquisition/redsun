import dependency_injector.providers as dip

from ._base import (
    BaseStorage,
    OpenStore,
    SinkFactory,
    StorageIO,
    StoreStateError,
    StreamSpec,
)
from ._path_provider import PathSignals, SessionPathProvider
from ._registry import clear_registry, get_storage, register_storage, reset_group
from ._sink import FrameSink

PATH_PROVIDER = dip.Dependency(instance_of=SessionPathProvider)
"""Key for the session path provider shared by `StoragePresenter`."""

__all__ = [
    "PATH_PROVIDER",
    "BaseStorage",
    "FrameSink",
    "OpenStore",
    "PathSignals",
    "SessionPathProvider",
    "SinkFactory",
    "StorageIO",
    "StoreStateError",
    "StreamSpec",
    "clear_registry",
    "get_storage",
    "register_storage",
    "reset_group",
]
