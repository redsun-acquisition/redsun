---
icon: lucide/git-branch
---

# How derived products are stored

A derived product is an array that a component computes from a
[run](glossary.md#run) and keeps next to the data it came from, such as a
median over a scan or a filtered copy of every frame. The device and its
service write the run's own data; a derived product is the one thing `redsun`
writes, through a [`Writer`][redsun.writers.Writer].
[Write a derived product](../how-to/write-a-derived-product.md) shows every
step.

## Documents in, arrays in

A `Writer` takes two kinds of input, from two directions. Here is a component
that keeps the median of a camera's frames, cut down to the lines that talk to
its writer:

```python
from typing import Any

from event_model import DocumentRouter, RunStop

from redsun.writers import Writer


class MedianPresenter(DocumentRouter):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self._writer = Writer()
        self._writer.derive("camera_median", source="camera")

    def __call__(self, name: str, doc: dict[str, Any], validate: bool = False) -> Any:
        result = super().__call__(name, doc, validate)
        self._writer(name, doc)
        return result

    def stop(self, doc: RunStop) -> RunStop:
        self._writer.write("camera_median", self._median)
        return doc
```

The component receives the run's [documents](glossary.md#document) like any
[callback](glossary.md#callback), and passes each one on to the writer by
calling it. The documents tell the writer where the camera's frames went and
what shape they have, which is everything it needs to lay out the product.
They can't carry the product itself, though, because the component computes
it from the frames after they arrive. So the data reaches the writer the other
way, from the component, through `write`. Here `self._median` stands for what
the component computed while the run went on; a product written frame by
frame goes in through `append` instead.

The session never subscribes a writer itself. The component forwards the
documents after handling each one, so the writer sees the run's `stop` only
after the component has written its result.

## Where a product is stored

A product goes where its source data went. `derive("camera_median",
source="camera")` says that the median is laid out like one camera frame and
belongs in the camera's store, and the run fills in the rest: the frame's
shape and type from the camera's description, and the store from the document
naming it. Because the device chose the format and the store
([ADR 0013](decisions/0013-acquisition-storage-belongs-to-the-device.md)), the
product follows that choice rather than making one of its own.

For a product the run says nothing about, `declare` gives the shape, the type
and the store up front instead:

```python
self._writer.declare("mask", shape=(512, 512), dtype="uint8", store=store_uri)
```

## Declaring products up front

Both `derive` and `declare` belong in the constructor, before the run starts,
because the stores can't grow new arrays later. `acquire-zarr` sizes a store's
arrays once, when its stream opens, and `ome-writers` allocates every frame of
an image at that same moment, so a product can't join a store whose stream is
open. For the same reason, a product that gets a store of its own is written
all at once rather than frame by frame.
