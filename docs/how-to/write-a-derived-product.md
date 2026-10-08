---
icon: lucide/layers
---

# How to write a derived product

A component that computes something from a
[run](../explanation/glossary.md#run), such as a median over a scan or a
filtered copy of each frame, writes the result against the store the device
wrote. The acquisition belongs to the service and its device ([ADR
0013](../explanation/decisions/0013-acquisition-storage-belongs-to-the-device.md)),
so a [derived product](../explanation/glossary.md#derived-product) is the one
thing `redsun` writes. [Derived products](../explanation/derived-products.md)
says why a product is handed over rather than carried by a
[document](../explanation/glossary.md#document).

Step through what the component, its writer and the store do during one run:

```d2 title="A derived product through one run"
...@diagrams/style
shape: sequence_diagram
component: "your component" {class: step}
writer: Writer {class: step}
store: "the device's store" {
  class: file
  tooltip: The store the stream_resource document names, written by the device during the run. Beside an OME-Zarr image, the product gets a store of its own instead.
}
component -> writer: "constructor: derive(product, source=...)"
component -> writer: "descriptor of source:\nframe shape and dtype" {style.opacity: 0}
component -> writer: "stream_resource of source:\nthe store" {style.opacity: 0}
component -> writer: "event: append(product, frames)" {style.opacity: 0}
writer -> store: "first append or write: open a stream\nwith every product of the store" {
  style.opacity: 0
}
component -> writer: "stop: write(product, data)" {style.opacity: 0}
writer -> store: "stop of the run: close the stream,\nwrite the metadata" {style.opacity: 0}
steps: {
  1: {(component -> writer)[1].style.opacity: 1}
  2: {(component -> writer)[2].style.opacity: 1}
  3: {(component -> writer)[3].style.opacity: 1}
  4: {(writer -> store)[0].style.opacity: 1}
  5: {(component -> writer)[4].style.opacity: 1}
  6: {(writer -> store)[1].style.opacity: 1}
}
```

## Install the extra

The `zarr` extra brings `acquire-zarr`, which every product needs. The
`ome-zarr` extra also brings `ome-writers[acquire-zarr]`, which you need only to
write beside an OME-Zarr image.

```bash
pip install "redsun[zarr]"
pip install "redsun[ome-zarr]"
```

Without `acquire-zarr`, importing `redsun.writers` raises `ImportError` naming
the extra. Without `ome-writers`, the first product placed beside an image
raises it.

## Declare each product before the run

A [`Writer`][redsun.writers.Writer] holds every product a component writes.
Declare them in the constructor, because a store's arrays are all sized when
its stream opens:

```python
from collections.abc import Sequence

from event_model import DocumentRouter

from redsun.writers import Writer


class MedianPresenter(DocumentRouter):
    def __init__(self, name: str, *, sources: Sequence[str]) -> None:
        super().__init__()
        self.name = name
        self._sources = tuple(sources)
        self._writer = Writer()
        for source in self._sources:
            self._writer.derive(f"{source}_median", source=source)
            self._writer.derive(f"{source}_filtered", source=source)
```

`sources` holds the [data keys](../explanation/glossary.md#data-key) to compute
from, and it comes from the session file like any other argument of a
component.

`derive` takes the layout and the store from the run's documents. A key described as `external: STREAM:` leads its shape with
the frames per event, which `derive` drops. For a product the run says nothing
about, `declare` gives both up front:

```python
self._writer.declare("mask", shape=(512, 512), dtype="uint8", store=store_uri)
```

## Forward the documents

The writer learns about the run from its documents, so forward each one after
the component's own dispatch. That way the writer sees `stop` only after the
component has written what it computes there:

```python
def __call__(self, name: str, doc: dict[str, Any], validate: bool = False) -> Any:
    result = super().__call__(name, doc, validate)
    self._writer(name, doc)
    return result
```

## Hand the data over

Use `append` for a product you write as the run goes, one frame or a stack of
frames at a time, and `write` for one you compute at the end and hand over
whole. Below, `source` is one of the data keys, and `filtered` and `median` are
the arrays the component computed for it:

```python
def event(self, doc: Event) -> Event:
    ...
    self._writer.append(f"{source}_filtered", filtered)
    return doc


def stop(self, doc: RunStop) -> RunStop:
    self._writer.write(f"{source}_median", median, metadata={"derived_from": source})
    return doc


def shutdown(self) -> None:
    self._writer.shutdown()
```

The store's stream closes at the `stop` of the run that named the store. A
run nested inside another sees what the outer run
declared, so a product computed at the nested run's stop can go to the outer
run's store.

!!! warning "A product declared after the stream opens"

    The writer refuses a product declared once its store's stream is open, with
    a `WriterError` naming it. Declare every product in the constructor.

`shutdown` closes whatever a session that ended mid-run left open, so the store
stays readable.

## Where the product goes

The `stream_resource` document names the format and the store, and the writer
reads the store's root to decide where the product goes. `redsun.writers`
exports the two mimetypes it knows as `ZARR` and `OME_ZARR`, for a device that
writes either into its documents:

| Mimetype | Store root | Product goes | `write` returns |
| --- | --- | --- | --- |
| `application/x-zarr` | a plain group | a key of the same store | the store's URI |
| `application/x-ome-zarr` | a plain group | a key of the same store, with NGFF metadata of its own | the store's URI |
| `application/x-ome-zarr` | an image, a plate, a `bioformats2raw` layout | a store of its own beside it, named `<store>_<data_key>.ome.zarr` | the new store's URI |

Adding a key to a root that carries OME-Zarr metadata drops it, which is why
the product goes beside such a root. A store of its own is written all at once,
because `ome-writers` allocates every frame at open, so `append` to it is
refused and `write` finishes it at once. If a `stream_resource` has a mimetype
the writer doesn't know, the writer logs it once and skips the product for that
run.

## What is written with the product

Two mappings land on the product's own group, never on the store's root, which
a stream closing on the store rewrites. One is the `metadata` you give to
`write`, as given, and the other is a `redsun` mapping the writer fills from the
run.

| Key | Value |
| --- | --- |
| `run_start` | the uid of the run, `null` for a product written outside one |
| `source` | the [data key](../explanation/glossary.md#data-key) a `derive`d product was laid out and stored as |
| `resource_uri` | the URI of the store the `stream_resource` named |
| `written` | when the product's stream closed, ISO 8601, UTC |

## Register it, or not

A writer registers nothing, so a product that belongs in a catalog has to be
put there by the same component. Writing and registering are separate choices.
