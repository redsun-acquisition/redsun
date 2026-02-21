from typing import Any

from sunflare.virtual import RedSunConfig
from typing_extensions import NotRequired

__all__ = ["AppConfig", "StorageConfig"]


class StorageConfig(RedSunConfig, total=False):
    """Configuration for the storage backend.

    Parameters
    ----------
    backend : str
        Storage backend identifier. Currently only ``"zarr"`` is supported.
    base_path : str
        Base directory for the store root as a plain filesystem path
        (e.g. ``"C:/data/scans"`` or ``"/data/scans"``).
        Defaults to ``~/redsun-storage/<session>`` — created automatically if absent.
    filename_provider : str
        Filename strategy: ``"auto_increment"`` (default), ``"uuid"``, or
        ``"static"``.
    filename : str
        Static filename — only used when *filename_provider* is ``"static"``.
    """

    backend: NotRequired[str]
    base_path: NotRequired[str]
    filename_provider: NotRequired[str]
    filename: NotRequired[str]


class AppConfig(RedSunConfig, total=False):
    """Extended configuration for Redsun application containers.

    Extends [`RedSunConfig`][sunflare.virtual.RedSunConfig`] with component sections
    used by the application layer. These are **not** propagated to components.
    """

    devices: NotRequired[dict[str, Any]]
    presenters: NotRequired[dict[str, Any]]
    views: NotRequired[dict[str, Any]]
    storage: NotRequired[StorageConfig]
