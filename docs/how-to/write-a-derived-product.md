# Write a derived product

A component computing something from a finished acquisition, a median over a
stack or a mask, writes it against the store the device already wrote. The
acquisition's own bytes belong to the service and its device
([ADR 0013](../explanation/decisions/0013-acquisition-storage-belongs-to-the-device.md)),
and a derived product is the one thing `redsun` writes.

## Install the extra

The writers need the packages of the formats they write:

```bash
pip install redsun[zarr]
```

A writer called without its package raises `WriterError` naming the extra,
rather than failing on an import.

## Pick the writer by mimetype

The `StreamResource` document names the format and the store. Read it and
import the module that writes that format:

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

Every writer takes the same arguments, named for the document's own fields, so
nothing is renamed between reading a document and calling a writer:

```python
def write(
    uri: str,
    *,
    data_key: str,
    data: NDArray[Any],
    metadata: Mapping[str, Any] | None = None,
) -> str: ...
```

Two modules ship today: `zarr` for `application/x-zarr` and `ome_zarr` for
`application/x-ome-zarr`.

## Read the returned URI

The writer decides where the product lands by reading the store it is given,
and the return value says where it went. It is the argument when the product
was added to that store, and a new URI when it was written beside it:

| Store | Where the product goes | Returned |
| --- | --- | --- |
| root is a plain group | another key in the same store | the argument |
| root is the image | a store of its own, beside it | the new store |

A store whose root is the image cannot take another key: adding one drops the
root's `ome` block and the image stops being OME-Zarr. `ome_zarr.write` writes
a sibling instead, and `zarr.write` refuses the store rather than damaging it.

Metadata is written to the product's own group, never the store's root, since
a stream closing on the store rewrites the root's metadata and would drop it.

## Register it, or not

A writer registers nothing. If the product belongs in a catalog, put it there
in the same callback; the two are chosen per product and `redsun` does not
chain them.
