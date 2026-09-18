# 13. Acquisition storage belongs to the device

Date: 2026-09-18

## Status

Accepted. Supersedes [2. Storage dual-context redesign](0002-storage-dual-context-redesign.md).

## Context

ADR 0002 designed a storage layer inside `redsun`: `BaseStorage` holding a
format backend, `StreamSpec` declaring a stream, `FrameSink` carrying frames
and `OpenStore` writing them. It assumes 2D frames enter the application and
are appended one at a time, which is what a camera driven from the session
process produces.

`0.13.0rc0` added the service layer. A device backed by a service hands the
application no frames: the service, or the `ophyd-async` writer beside it,
writes a multidimensional acquisition to disk and the device emits
`StreamResource` and `StreamDatum` documents pointing at it. Routing those
frames back through a sink costs a copy and a format the service did not
choose.

[redsun#116](https://github.com/redsun-acquisition/redsun/issues/116) tested
that path and concluded, in its reporter's words, that "the rc0 release
addresses the RedSun service-layer issue for my use case" and that no new
`redsun` multidimensional storage API is wanted. The formats a facility needs,
OME-Zarr, OME-TIFF or a local one, are a service's decision, and each detector
owning its own store keeps buffer ownership, completion and partial failure
local to the detector that produced the data.

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

A session still decides where its files go. `SessionPathProvider` moves to
`redsun.path_provider`, and the container builds one per session and passes it
to every device taking a `path_provider` keyword.

## Consequences

A device that used `BaseStorage` has to write its own data, through its
service or an `ophyd-async` writer. A camera owning its writer is shaped
differently from one feeding a sink, so there is no line-for-line
substitution.

`StreamDatum` ranges are whatever the device emits. `FrameRouter` counted
frames as they were written, which is why ranges were contiguous and the array
was in arrival order; nothing replaces it, and `redsun` guarantees nothing
about the order or the completeness of the ranges a device reports.

A derived product, such as a median computed over a run, is written by the
component that computes it, against the store named in the `StreamResource`
document.
