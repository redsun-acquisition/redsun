from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("redsun")
except PackageNotFoundError:
    __version__ = "unknown"
