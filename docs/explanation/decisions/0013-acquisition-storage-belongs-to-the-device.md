# 13. Acquisition storage belongs to the device

Date: 2026-09-18

## Status

Accepted. Supersedes [2. Storage dual-context redesign](0002-storage-dual-context-redesign.md).

## Context

ADR 0002 put a storage layer inside `redsun`: `BaseStorage` with a format
backend, `StreamSpec` declaring a stream, `FrameSink` carrying frames and
`OpenStore` writing them. It assumes 2D frames entering the application one at
a time, as from a camera driven by the session process.

`0.13.0rc0` added services. A service-backed device hands the application no
frames: the service, or the `ophyd-async` writer beside it, writes a
multidimensional acquisition, and the device emits `StreamResource` and
`StreamDatum` documents pointing at it. Routing frames back through a sink
costs a copy and a format the service did not choose.

[redsun#116](https://github.com/redsun-acquisition/redsun/issues/116) tested
that path and concluded, in its reporter's words, that "the rc0 release
addresses the RedSun service-layer issue for my use case" and that no new
`redsun` multidimensional storage API is wanted. Formats, OME-Zarr, OME-TIFF
or a local one, are a service's decision, and a detector owning its store keeps
buffers, completion and partial failure local to it.

## Decision

`redsun` writes no acquisition bytes. The layers are:

| Concern | Owner |
| --- | --- |
| format, dimensions, chunking, durability, completion | the service and its device |
| `mimetype` and `parameters["path"]` on the emitted documents | the device |
| derived products, computed from documents after the fact | a `redsun` presenter |

`redsun.storage`'s shim is removed: `BaseStorage`, `StreamSpec`, `OpenStore`,
`StorageIO`, `SinkFactory`, `FrameSink`, `FrameRouter`, the storage registry
and the backends, with the `StoragePresenter` and `StorageView` built-ins.

A session still decides where files go: `SessionPathProvider` moves to
`redsun.path_provider`, and the container passes one per session to every
device taking a `path_provider` keyword.

## Consequences

A device that used `BaseStorage` writes its own data, through its service or
an `ophyd-async` writer. A camera owning its writer is shaped differently from
one feeding a sink, so there is no line-for-line substitution.

`StreamDatum` ranges are whatever the device emits. `FrameRouter` kept them
contiguous and in arrival order; nothing replaces it, and `redsun` guarantees
neither order nor completeness.

A derived product, such as a median over a run, is written by the component
computing it, against the store named in the `StreamResource` document.
