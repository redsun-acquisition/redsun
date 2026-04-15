from importlib.metadata import PackageNotFoundError, version

from redsun.containers import (
    AppContainer,
    Frontend,
    declare_device,
    declare_presenter,
    declare_view,
)

try:
    __version__ = version("redsun")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = [
    "AppContainer",
    "Frontend",
    "declare_view",
    "declare_presenter",
    "declare_device",
    "__version__",
]
