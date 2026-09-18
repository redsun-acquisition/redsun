# Keep a catalog of runs

A session can keep a `tiled` catalog beside its files, so its runs can be read
back through the `tiled` client API. The catalog is a server the session starts
on this machine; what goes into it is up to the session's components, since
`redsun` writes no acquisition data itself
([ADR 0013](../explanation/decisions/0013-acquisition-storage-belongs-to-the-device.md)).

## Install the extra

```bash
pip install redsun[tiled]
```

The extra installs `tiled` and `ome-tiled`. It installs nothing on Python
3.14, which `tiled` does not support yet.

## Turn the catalog on

Add a `catalog` key to the session's `storage` section. Present and empty is
enough:

```yaml
storage:
  catalog:
```

The catalog lives in `<base_dir>/<session>/catalog`, beside the session's
acquisition files, so everything a session produced is under one directory. A
session asking for a catalog without the extra installed is refused when it is
built, naming the extra.

The catalog reads files from `<base_dir>/<session>`. A service writing
somewhere else, set by its own configuration, needs that directory listed:

```yaml
storage:
  catalog:
    readable:
      - /data/camera
```

`tiled` checks this when a file is read, not when it is registered: a run
pointing at a file outside every readable directory is recorded, and reading
its data fails.

The readable directories are fixed when the catalog starts, so the root cannot
change while it runs: `SessionPathProvider.set_base_dir` raises
`RuntimeError`. Choose the root with `storage.base_dir` before the session
starts, and list any other disk a service writes to under `readable`.

## Record runs

Nothing is written into the catalog unless a component does it.
`bluesky-tiled-plugins`' `TiledWriter` writes whole runs, and a presenter can
register one as a document callback when the session has a catalog:

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

[`CATALOG`][redsun.catalog.CATALOG] gives the catalog's
[`CatalogAddress`][redsun.catalog.CatalogAddress], or `None` in a session
without one. The presenter owning the `RunEngine` subscribes the registered
callbacks, as [the virtual container page](../explanation/architecture/virtual.md)
shows, so the writer receives every run.

## What a device has to emit

`TiledWriter` registers a detector's files from its `StreamResource` document,
so the document has to describe them:

- `mimetype` matches the bytes: `application/x-ome-zarr` for an OME-Zarr
  store, `application/x-zarr` for a plain Zarr array.
- `uri` names the OME-Zarr store, or its image. For plain Zarr it names the
  array itself, since `TiledWriter` does not read `parameters["path"]`.

An OME-Zarr image is registered with the shape, chunks and axis names its store
holds, whatever the shape of each row in the stream: the session registers
`ome-tiled`'s consolidator for `TiledWriter` when it starts the catalog.

## Read a run back

Any component can open its own client:

```python
from tiled.client import from_uri

address = container.try_require(CATALOG)
client = from_uri(address.uri)
image = client[run_uid]["primary"]["det"].read()
```

A derived product can go into the catalog the same way, with
`client[run_uid].write_array(...)`, or into the acquisition's store, as
[Write a derived product](write-a-derived-product.md) describes.

What a client can do to a registered file is covered in
[The session catalog](../explanation/catalog.md).
