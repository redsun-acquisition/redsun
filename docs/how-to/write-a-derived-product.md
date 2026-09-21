# Write a derived product

A component computing something from a finished acquisition, such as a median
or a mask, writes it against the store the device wrote. The acquisition
belongs to the service and its device
([ADR 0013](../explanation/decisions/0013-acquisition-storage-belongs-to-the-device.md));
a derived product is the one thing `redsun` writes.

## Install the extra

One per format: `zarr` brings `acquire-zarr`, `ome-zarr` brings
`ome-writers[acquire-zarr]`, which is more than a plain Zarr product needs.

```bash
pip install redsun[zarr]      # redsun.storage.writers.zarr
pip install redsun[ome-zarr]  # redsun.storage.writers.ome_zarr
```

Without it, importing the writer module raises `ImportError` naming the
extra.

## Pick the writer by mimetype

The `StreamResource` document names the format and the store:

```python
from redsun.storage.writers import ome_zarr


def on_stop(self, resource: StreamResource, median: NDArray[np.uint16]) -> None:
    if resource["mimetype"] != "application/x-ome-zarr":
        self.logger.warning(f"Cannot write a median into {resource['mimetype']!r}.")
        return
    product_uri = ome_zarr.write(
        resource["uri"],
        data_key="det_median",
        data=median,
        metadata={"derived_from": resource["data_key"]},
    )
```

Every writer takes the same arguments, named after the document's fields:

```python
def write(
    uri: str,
    *,
    data_key: str,
    data: NDArray[Any],
    metadata: Mapping[str, Any] | None = None,
) -> str: ...
```

`zarr` writes `application/x-zarr`, `ome_zarr` writes `application/x-ome-zarr`.

## Read the returned URI

The writer reads the store and decides where the product goes; the return
value says where:

| Store root | Product goes | Returned |
| --- | --- | --- |
| a plain group | another key in the same store | the argument |
| OME-Zarr metadata: an image, a plate, a `bioformats2raw` layout | a store of its own, beside it | the new store |

Adding a key to a root with OME-Zarr metadata drops its `ome` block, so
`ome_zarr.write` writes a sibling and `zarr.write` refuses the store.

Metadata goes to the product's own group, never the root: a stream closing on
the store rewrites the root's metadata.

## Register it, or not

A writer registers nothing. A product that belongs in a catalog is put there
by the same callback; the two are separate choices.
