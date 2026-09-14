from typing import Any, NotRequired, Required

from typing_extensions import TypedDict

__all__ = ["RedSunConfig"]


class RedSunConfig(TypedDict, total=False):
    """Base configuration schema of a ``redsun`` application."""

    schema_version: Required[float]
    """Plugin schema version."""

    frontend: Required[str]
    """Frontend toolkit identifier (e.g. `"pyqt"`, `"pyside"`)."""

    name: NotRequired[str]
    """Session identity.

    Names the session's application, so two sessions in one process must not
    share it. A container omitting it is named after its own class, which is
    distinct per session where a shared constant would not be. A session built
    from a configuration alone has no class of its own, so there it is
    required.
    """

    metadata: NotRequired[dict[str, Any]]
    """Session metadata."""
