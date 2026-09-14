from typing import Any, NotRequired, Required

from typing_extensions import TypedDict

__all__ = ["RedSunConfig"]


class RedSunConfig(TypedDict, total=False):
    """Base configuration schema of a ``redsun`` application."""

    schema_version: Required[float]
    """Plugin schema version."""

    frontend: Required[str]
    """Frontend toolkit identifier (e.g. `"pyqt"`, `"pyside"`)."""

    session: NotRequired[str]
    """Session display name, `"redsun"` if not given."""

    metadata: NotRequired[dict[str, Any]]
    """Session metadata."""
