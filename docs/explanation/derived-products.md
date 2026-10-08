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

A `Writer` takes two kinds of input, from two directions. Step through to see
them reach it:

```d2 title="What reaches a writer"
...@diagrams/style
grid-rows: 2
grid-columns: 2
grid-gap: 120
run: "the run" {
  class: step
  tooltip: The RunEngine emits the run's documents while the camera and its service write the frames.
}
component: "component\na document callback" {class: hidden}
store: "the camera's store" {
  class: file
  tooltip: The device and its service chose the format and the place, and wrote the frames there.
}
writer: "Writer" {class: hidden}
run -> store: "frames"
run -> component: "documents" {style.opacity: 0}
component -> writer: "documents" {style.opacity: 0}
writer -> store: "the product" {style.opacity: 0}
steps: {
  1: {
    component.class: step
    component.tooltip: The component receives the run's documents like any callback, and computes its product from the frames as they arrive.
    (run -> component)[0].style.opacity: 1
  }
  2: {
    writer.class: step
    writer.tooltip: The documents tell the writer where the frames went and what shape they have, which is everything it needs to lay out the product.
    (component -> writer)[0].style.opacity: 1
  }
  3: {
    (component -> writer)[0].label: "documents,\nthen the product"
    component.tooltip: The documents can't carry the product, because the component computes it after the frames arrive. So the component hands the data over itself, with write, or with append frame by frame.
  }
  4: {
    (writer -> store)[0].style.opacity: 1
    writer.tooltip: The writer puts the product next to the frames, in the store the device chose.
  }
}
```

Here is a component that keeps the median of a camera's frames, cut down to the
lines that talk to its writer:

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

`self._median` stands for what the component computed while the run went on;
a product written frame by frame goes in through `append` instead. The session
never subscribes a writer itself. The component forwards each document after
handling it, so the writer sees the run's `stop` only after the component has
written its result.

## Where a product is stored

A product goes where its source data went, following the device's choice of
format and store
([ADR 0013](decisions/0013-acquisition-storage-belongs-to-the-device.md)).
`derive("camera_median", source="camera")` lays the median out like one camera
frame in the camera's store, and two documents of the run fill in the rest:

```d2 title="What derive takes from the run"
...@diagrams/style
direction: right
product: "camera_median\nderive(source=\"camera\")" {class: step}
descriptor: "descriptor\nnaming camera" {
  class: file
  tooltip: The run's description of the stream the camera belongs to.
}
resource: "stream_resource\nnaming camera" {
  class: file
  tooltip: The document the device emits when it opens the file its frames go to.
}
layout: "the frame's\nshape and dtype" {class: hidden}
store: "the store's\nURI and format" {class: hidden}
descriptor -> layout {style.opacity: 0}
resource -> store {style.opacity: 0}
layout -> product {style.opacity: 0}
store -> product {style.opacity: 0}
steps: {
  1: {
    layout.class: step
    layout.tooltip: A key the camera streams leads its shape with the frames per event, which derive drops.
    (descriptor -> layout)[0].style.opacity: 1
    (layout -> product)[0].style.opacity: 1
  }
  2: {
    store.class: step
    store.tooltip: The format is the document's mimetype. The writer knows plain Zarr and OME-Zarr, and skips the product for a run whose store has another, logging it once.
    (resource -> store)[0].style.opacity: 1
    (store -> product)[0].style.opacity: 1
  }
}
```

For a product the run says nothing about, `declare` gives the shape, the type
and the store up front instead:

```python
self._writer.declare("mask", shape=(512, 512), dtype="uint8", store=store_uri)
```

## Declaring products up front

Both `derive` and `declare` belong in the constructor, before the run starts,
because the stores can't grow new arrays later. Step through a run to see when
each part happens:

```d2 title="A product over one run"
...@diagrams/style
shape: sequence_diagram
component: "component"
writer: "Writer"
store: "the camera's store"
component -> writer: "derive, in the constructor"
component -> writer: "documents: start,\ndescriptor, stream_resource" {style.opacity: 0}
component -> writer: "first append or write" {style.opacity: 0}
writer -> store: "open the stream:\nsize every array" {style.opacity: 0}
component -> writer: "append a product declared\nsince: WriterError" {style.opacity: 0}
component -> writer: "documents: stop" {style.opacity: 0}
writer -> store: "close the stream,\nwrite the metadata" {style.opacity: 0}
steps: {
  1: {
    (component -> writer)[1].style.opacity: 1
  }
  2: {
    (component -> writer)[2].style.opacity: 1
    (writer -> store)[0].style.opacity: 1
    (writer -> store)[0].tooltip: The stream opens with every product of that store known by then. acquire-zarr sizes a store's arrays once, at this moment, and ome-writers allocates every frame of an image.
  }
  3: {
    (component -> writer)[3].style.opacity: 1
  }
  4: {
    (component -> writer)[4].style.opacity: 1
    (writer -> store)[1].style.opacity: 1
    (writer -> store)[1].tooltip: The metadata is the mapping given to write, and a redsun mapping naming the run, the source, the store and the time.
  }
}
```

A product can't join a store whose stream is open. For the same reason, a
product that gets a store of its own, beside an OME-Zarr image, is written all
at once rather than frame by frame: `write` opens and finishes that store in
one call, and `append` to it is refused.
