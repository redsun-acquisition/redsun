from importlib.metadata import PackageNotFoundError, version

from redsun.containers import AppContainer, Frontend, device, presenter, view

try:
    __version__ = version("redsun")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = ["AppContainer", "Frontend", "view", "presenter", "device", "__version__"]
