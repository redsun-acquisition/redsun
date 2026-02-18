from importlib.metadata import PackageNotFoundError, version

from redsun.containers import AppContainer, component

try:
    __version__ = version("redsun")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = ["AppContainer", "component", "__version__"]
