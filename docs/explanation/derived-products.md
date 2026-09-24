---
icon: lucide/git-branch
---

# How derived products are stored

A derived product is an array a component computes from a run and keeps next
to the data it came from, such as a median over a scan or a filtered copy
of every frame. [Write a derived product](../how-to/write-a-derived-product.md)
shows how one is written.

## A product is not a document

`bluesky` carries acquisition data as documents, and `suitcase`, its family
of exporters, writes a run to a file by reading them: every exporter is a
`DocumentRouter` that serializes what the documents carry. A derived product
has the same shape and a different job. The documents say where the
acquisition went and what its arrays look like; the product itself is
computed by a component after the fact, and no document carries it.

So [`Writer`][redsun.writers.Writer] takes the two apart. The
documents go in through `__call__`, as with any callback, and tell the
writer the layout and the store of each product. The data goes in through
`append` and `write`, from the component that computed it. The session
registers no writer as a callback: the component forwards the documents
itself, which keeps the order in its hands, so `stop` reaches the writer
after the component wrote its result there.

## A product follows its source

A product is usually laid out and stored as the data key it was computed
from: a median of a camera's frames has a frame's shape and belongs in the
camera's store. `derive` says so once, and the run fills in the rest. The
device chose the format and the store
([ADR 0013](decisions/0013-acquisition-storage-belongs-to-the-device.md)),
and the product follows that choice rather than making one of its own.

## Every array is declared at open

`acquire-zarr` sizes a store's arrays once, when its stream opens, and
`ome-writers` allocates every frame of an image at the same moment. A
product cannot join a store whose stream is open, which is why the how-to
declares every product in the constructor and why a store of its own is
written whole rather than frame by frame.
