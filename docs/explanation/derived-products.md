---
icon: lucide/git-branch
---

# How derived products are stored

A derived product is an array that a component computes from a
[run](glossary.md#run) and keeps next to the data it came from, such as a
median over a scan or a filtered copy of every frame.
[Write a derived product](../how-to/write-a-derived-product.md) shows how to
write one.

## Products and documents

A derived product isn't part of the documents a run emits, so `redsun` handles
the two separately. [`bluesky`](glossary.md#bluesky) carries acquisition data
as [documents](glossary.md#document), and `suitcase`, its family of exporters,
writes a run to a file by reading them: every exporter is a `DocumentRouter`
that serializes what the documents carry. A derived product has the same
shape and a different job. The documents say where the acquisition went and
what its arrays look like, but a component computes the product after the
fact, and no document carries it.

So [`Writer`][redsun.writers.Writer] keeps the two apart. The documents go in
through `__call__`, as with any callback, and tell the writer the layout and
the store of each product. The data goes in through `append` and `write`, from
the component that computed it. The session doesn't register any writer as a
callback. Instead, the component forwards the documents itself, which keeps
their order in its hands, so `stop` reaches the writer only after the
component has written its result there.

## Where a product is stored

A product goes where its source data went. It's usually laid out and stored
the same way as the [data key](glossary.md#data-key) it was computed from: a
median of a camera's frames has the shape of one frame and belongs in the
camera's store. You say so once, with `derive`, and the run fills in the rest.
Because the device chose the format and the store
([ADR 0013](decisions/0013-acquisition-storage-belongs-to-the-device.md)), the
product follows that choice rather than making one of its own.

## Declaring products up front

You declare every product before the run starts, because the stores can't grow
new arrays later. `acquire-zarr` sizes a store's arrays once, when its stream
opens, and `ome-writers` allocates every frame of an image at that same
moment. A product can't join a store whose stream is open. That's why the
how-to declares every product in the constructor, and why a store of its own
is written whole rather than frame by frame.
