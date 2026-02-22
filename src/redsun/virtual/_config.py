from typing import Any

from typing_extensions import NotRequired, Required, TypedDict

__all__ = ["RedSunConfig"]


class RedSunConfig(TypedDict, total=False):
    """Base configuration schema for Redsun applications."""

    schema_version: Required[float]
    """Plugin schema version."""

    frontend: Required[str]
    """Frontend toolkit identifier (e.g. `"pyqt"`, `"pyside"`)."""

    session: NotRequired[str]
    """Session display name. If not provided, default is `"redsun"`."""

    metadata: NotRequired[dict[str, Any]]
    """Additional session-specific metadata to include in the configuration."""
