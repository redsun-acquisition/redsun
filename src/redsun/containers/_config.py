from typing import Any

from sunflare.virtual import RedSunConfig
from typing_extensions import NotRequired

__all__ = ["AppConfig"]


class AppConfig(RedSunConfig, total=False):
    """Extended configuration for Redsun application containers.

    Extends :class:`~sunflare.virtual.RedSunConfig` with component sections
    used by the application layer. These are **not** propagated to components.
    """

    devices: NotRequired[dict[str, Any]]
    presenters: NotRequired[dict[str, Any]]
    views: NotRequired[dict[str, Any]]
