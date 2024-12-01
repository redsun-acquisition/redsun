# noqa: D100, D104
try:
    from .handler import BlueskyHandler
except ImportError:

    class BlueskyHandler:  # type: ignore[no-redef] # noqa: D101
        ...


__all__ = ["BlueskyHandler"]
