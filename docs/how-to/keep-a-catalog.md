---
icon: lucide/library
---

# How to keep a catalog of runs

A session can run a [`tiled`](../explanation/glossary.md#tiled) server beside
its files, so you can read its [runs](../explanation/glossary.md#run) back
through the `tiled` client. What goes into it is up to the session's
components, because `redsun` writes no acquisition data itself
([ADR 0013](../explanation/decisions/0013-acquisition-storage-belongs-to-the-device.md)).

## Install the extra

```bash
pip install "redsun[tiled]"
```

It installs `tiled` and `ome-tiled`, but nothing on Python 3.14, which `tiled`
doesn't support yet.

## Turn the catalog on

Add a `catalog` key to the `storage` section. An empty one is enough:

```yaml
storage:
  catalog:
```

The catalog lives in `<base_dir>/<session>/catalog`, beside the session's
files. Without the extra, the session refuses to build.

The catalog reads files from `<base_dir>/<session>`. List any other directory a
service writes to:

```yaml
storage:
  catalog:
    readable:
      - /data/camera
```

!!! warning "A file outside the readable directories"

    `tiled` checks the readable directories when it reads a file, not when the
    file is registered, so a file outside every one of them is recorded and
    then fails to read. List the directory under `readable` before you start.

The readable directories are fixed when the catalog starts, so
`SessionPathProvider.set_base_dir` raises `RuntimeError` while it runs. Choose
the root with `storage.base_dir` before starting.

## Record runs

Nothing enters the catalog unless a component puts it there, and the
`TiledWriter` of `bluesky-tiled-plugins` writes whole runs. The presenter that
owns the [`RunEngine`](../explanation/glossary.md#runengine) asks for the
catalog's address and subscribes a writer:

```python
from bluesky_tiled_plugins import TiledWriter
from tiled.client import from_uri

from redsun.catalog import CatalogAddress
from redsun.engine import RunEngine


class AcquisitionPresenter:
    def __init__(self, name: str, *, address: CatalogAddress | None = None) -> None:
        self.name = name
        self.engine = RunEngine()
        if address is not None:
            self.engine.subscribe(TiledWriter(from_uri(address.uri)))
```

A parameter typed [`CatalogAddress`][redsun.catalog.CatalogAddress] receives
the catalog's address, or `None` when the session has no catalog or it failed
to start.

## What a device has to emit

`TiledWriter` registers a detector's files from its
[`StreamResource`](../explanation/glossary.md#streamresource):

- `mimetype` matches the bytes: `application/x-ome-zarr` for OME-Zarr,
  `application/x-zarr` for a plain Zarr array.
- `uri` names the OME-Zarr store or its image. For plain Zarr it names the
  array itself: `TiledWriter` ignores `parameters["path"]`.

An OME-Zarr image is stored with the shape, chunks and axis names its store
holds, whatever the shape of each row: the session registers `ome-tiled`'s
consolidator for `TiledWriter`.

## Read a run back

Any component can open its own client, from the same address:

```python
from tiled.client import from_uri

client = from_uri(address.uri)
image = client[run_uid]["primary"]["det"].read()
```

You can put a [derived product](../explanation/glossary.md#derived-product) into the catalog with
`client[run_uid].write_array(...)`, or into the acquisition's store
([Write a derived product](write-a-derived-product.md)). For what a client can
do to a registered file, see [The session catalog](../explanation/catalog.md).
