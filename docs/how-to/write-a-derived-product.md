# Write a derived product

A component computing something from a run, a median over a scan or a
filtered copy of each frame, writes it against the store the device wrote.
The acquisition belongs to the service and its device
([ADR 0013](../explanation/decisions/0013-acquisition-storage-belongs-to-the-device.md));
a derived product is the one thing `redsun` writes.
[Derived products](../explanation/derived-products.md) says why a product is
handed over rather than carried by a document.

## Install the extra

`zarr` brings `acquire-zarr`, which every product needs. `ome-zarr` brings
`ome-writers[acquire-zarr]` as well, needed only to write beside an OME-Zarr
image.

```bash
pip install redsun[zarr]
pip install redsun[ome-zarr]
```

Without `acquire-zarr`, importing `redsun.writers` raises
`ImportError` naming the extra. Without `ome-writers`, the first product
placed beside an image does.

## Declare each product before the run

A [`Writer`][redsun.writers.Writer] holds every product a component
writes. Declare them in the constructor, since a store's arrays are all sized
when its stream opens:

```python
from redsun.writers import Writer


class MyPresenter(Presenter, DocumentRouter):
    def __init__(self, name: str, devices: Mapping[str, Device]) -> None:
        super().__init__(name, devices)
        self._writer = Writer()
        for detector in self.detectors:
            self._writer.derive(f"{detector}_median", source=detector)
            self._writer.derive(f"{detector}_filtered", source=detector)
```

`derive` takes the layout and the store from the run: the `descriptor`
naming `source` gives the frame shape and dtype, the `stream_resource`
naming it gives the store. A key described as `external: STREAM:` leads
its shape with the frames per event, which is dropped. `declare` gives both up front, for a product the
run says nothing about:

```python
self._writer.declare("mask", shape=(512, 512), dtype="uint8", store=store_uri)
```

## Forward the documents

The writer learns the run from its documents. Forward each one after the
component's own dispatch, so the writer sees `stop` after the component
wrote what it computes there:

```python
def __call__(self, name: str, doc: dict[str, Any], validate: bool = False) -> Any:
    result = super().__call__(name, doc, validate)
    self._writer(name, doc)
    return result
```

## Hand the data over

`append` takes one frame, or a stack of frames, of a product written as the
run goes; `write` takes the whole of one computed at the end:

```python
def event(self, doc: Event) -> Event:
    ...
    self._writer.append(f"{detector}_filtered", filtered)
    return doc


def stop(self, doc: RunStop) -> RunStop:
    self._writer.write(
        f"{detector}_median", median, metadata={"derived_from": detector}
    )
    return doc


def shutdown(self) -> None:
    self._writer.shutdown()
```

The store's stream opens on the first `append` or `write` against it, with
every product of that store known by then, and closes at the `stop` of the
run that named the store. A run nested inside another sees what the outer
run declared, so a product computed at the nested run's stop can go to the
outer run's store. A product
declared after that is refused with a `WriterError` naming it. `shutdown`
closes whatever a session ending mid-run left open, so the store stays
readable.

## Where the product goes

The `stream_resource` document names the format and the store; the writer
reads the store's root and decides:

| Mimetype | Store root | Product goes | `write` returns |
| --- | --- | --- | --- |
| `application/x-zarr` | a plain group | a key of the same store | the store's URI |
| `application/x-ome-zarr` | a plain group | a key of the same store, with NGFF metadata of its own | the store's URI |
| `application/x-ome-zarr` | an image, a plate, a `bioformats2raw` layout | a store of its own beside it, named `<store>_<data_key>.ome.zarr` | the new store's URI |

Adding a key to a root carrying OME-Zarr metadata drops it, which is why the
product goes beside such a root. A store of its own is written whole, since
`ome-writers` allocates every frame at open: `append` to it is refused, and
`write` finishes it at once. A `stream_resource` with a mimetype the writer
does not know is logged once, and the product is skipped for that run.

## What is written with the product

Two mappings land on the product's own group, never on the store's root,
which a stream closing on the store rewrites: the `metadata` given to
`write`, as given, and a `redsun` mapping the writer fills from the run.

| Key | Value |
| --- | --- |
| `run_start` | the uid of the run, `null` for a product written outside one |
| `source` | the data key a `derive`d product was laid out and stored as |
| `resource_uri` | the URI of the store the `stream_resource` named |
| `written` | when the product's stream closed, ISO 8601, UTC |

## Register it, or not

A writer registers nothing. A product that belongs in a catalog is put there
by the same component; the two are separate choices.
