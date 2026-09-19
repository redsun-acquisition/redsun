# Keep a catalog of runs

A session can run a `tiled` server beside its files, so its runs can be read
back through the `tiled` client. What goes into it is up to the session's
components: `redsun` writes no acquisition data itself
([ADR 0013](../explanation/decisions/0013-acquisition-storage-belongs-to-the-device.md)).

## Install the extra

```bash
pip install redsun[tiled]
```

It installs `tiled` and `ome-tiled`, and nothing on Python 3.14, which `tiled`
does not support yet.

## Turn the catalog on

Add a `catalog` key to the `storage` section. Empty is enough:

```yaml
storage:
  catalog:
```

The catalog lives in `<base_dir>/<session>/catalog`, beside the session's
files. Without the extra, the session is refused at build.

It reads files from `<base_dir>/<session>`. List any other directory a service
writes to:

```yaml
storage:
  catalog:
    readable:
      - /data/camera
```

`tiled` checks this on read, not on registration: a file outside every
readable directory is recorded, and reading it fails.

The readable directories are fixed when the catalog starts, so
`SessionPathProvider.set_base_dir` raises `RuntimeError` while it runs. Choose
the root with `storage.base_dir` before starting.

## Record runs

Nothing enters the catalog unless a component puts it there.
`bluesky-tiled-plugins`' `TiledWriter` writes whole runs; a presenter can
register one as a document callback:

```python
from bluesky_tiled_plugins import TiledWriter
from tiled.client import from_uri

from redsun.catalog import CATALOG
from redsun.presenter import Presenter


class MyRecorder(Presenter):
    def __init__(self, name, devices, /, **kwargs):
        super().__init__(name, devices, **kwargs)

    def register_providers(self, container):
        address = container.try_require(CATALOG)
        if address is None:
            return
        container.register_callbacks(
            self, callback_map={self.name: TiledWriter(from_uri(address.uri))}
        )
```

[`CATALOG`][redsun.catalog.CATALOG] gives a
[`CatalogAddress`][redsun.catalog.CatalogAddress], or `None` without a
catalog. The presenter owning the `RunEngine` subscribes registered callbacks,
as [the virtual container page](../explanation/architecture/virtual.md) shows.

## What a device has to emit

`TiledWriter` registers a detector's files from its `StreamResource`:

- `mimetype` matches the bytes: `application/x-ome-zarr` for OME-Zarr,
  `application/x-zarr` for a plain Zarr array.
- `uri` names the OME-Zarr store or its image. For plain Zarr it names the
  array itself: `TiledWriter` ignores `parameters["path"]`.

An OME-Zarr image is stored with the shape, chunks and axis names its store
holds, whatever the shape of each row: the session registers `ome-tiled`'s
consolidator for `TiledWriter`.

## Read a run back

Any component can open its own client:

```python
from tiled.client import from_uri

address = container.try_require(CATALOG)
client = from_uri(address.uri)
image = client[run_uid]["primary"]["det"].read()
```

A derived product can go into the catalog with
`client[run_uid].write_array(...)`, or into the acquisition's store
([Write a derived product](write-a-derived-product.md)). What a client can do
to a registered file: [The session catalog](../explanation/catalog.md).
