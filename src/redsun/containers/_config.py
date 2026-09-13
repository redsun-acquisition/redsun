from typing import Any, NotRequired

from redsun.virtual import RedSunConfig

__all__ = ["AppConfig"]


class AppConfig(RedSunConfig, total=False):
    """Configuration of an application container.

    [`RedSunConfig`][redsun.virtual.RedSunConfig] plus the component sections,
    which the container reads and does not pass to components.
    """

    services: NotRequired[dict[str, Any]]
    devices: NotRequired[dict[str, Any]]
    presenters: NotRequired[dict[str, Any]]
    views: NotRequired[dict[str, Any]]
    wiring: NotRequired[list[dict[str, str]]]
    hooks: NotRequired[dict[str, dict[str, Any]]]
