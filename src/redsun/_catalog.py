from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tiled.server.simple import SimpleTiledServer

    from redsun.path_provider import SessionPathProvider

    from ._config import CatalogConfig


def require_tiled() -> None:
    """Raise `RuntimeError` naming each package of the ``tiled`` extra that is missing."""
    missing = [
        package
        for package in ("tiled", "ome_tiled", "bluesky_tiled_plugins")
        if importlib.util.find_spec(package) is None
    ]
    if not missing:
        return
    raise RuntimeError(
        "this session's 'storage' section has a 'catalog' key and "
        f"{', '.join(repr(package) for package in missing)} not installed. "
        "Install them with 'pip install redsun[tiled]', or drop the key. "
        "The extra installs nothing on Python 3.14, which tiled does not "
        "support yet."
    )


def start_catalog(
    config: CatalogConfig, provider: SessionPathProvider
) -> SimpleTiledServer:
    """Start a session's catalog in ``provider.session_dir / "catalog"``.

    The server reads from the session's directory and every one *config* adds,
    serves OME-Zarr images with their axis names, and has a ``TiledWriter`` in
    this process store them as their store holds them. *provider*'s root is
    locked once it runs. A server that started and then failed its setup is
    stopped before the error is raised.
    """
    # imported here: the tiled extra is optional, and require_tiled has
    # already refused a session asking for a catalog without it
    from ome_tiled import OME_ZARR_MIMETYPE, OmeZarrAdapter
    from ome_tiled.bluesky import register_consolidator
    from tiled.server.simple import SimpleTiledServer

    session_dir = provider.session_dir
    server = SimpleTiledServer(
        directory=session_dir / "catalog",
        readable_storage=[session_dir, *config.readable],
    )
    try:
        # TODO: let storage.catalog choose the adapters and consolidators
        # installed here, rather than always installing ome-tiled's

        # SimpleTiledServer takes no adapters; the first map holds the
        # catalog's own, ahead of tiled's defaults
        server.catalog.context.adapters_by_mimetype.maps[0][OME_ZARR_MIMETYPE] = (
            OmeZarrAdapter
        )
        register_consolidator()
        provider.lock_base_dir(
            "the session's catalog reads files only from the readable "
            "directories it started with; choose the root with "
            "storage.base_dir before the session starts"
        )
    except BaseException:
        server.close()
        raise
    return server
