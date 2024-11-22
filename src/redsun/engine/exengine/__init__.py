# noqa: D100, D104
try:
    from .handler import ExEngineHandler
except ImportError:

    class ExEngineHandler:  # type: ignore[no-redef] # noqa: D101
        ...


__all__ = ["ExEngineHandler"]
