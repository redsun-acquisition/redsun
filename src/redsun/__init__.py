# noqa : D100
try:
    from ._version import version as __version__  # type: ignore[import-not-found]
except ImportError:
    __version__ = "unknown"
