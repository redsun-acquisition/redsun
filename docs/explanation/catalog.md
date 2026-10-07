---
icon: lucide/database
---

# How the session catalog works

A session whose `storage` section has a `catalog` key runs a
[`tiled`](glossary.md#tiled) server on this machine, from build to shutdown,
to hold its [catalog](glossary.md#catalog).
[Keep a catalog of runs](../how-to/keep-a-catalog.md) shows how to use it.

## What `redsun` does

`redsun` starts the server, keeps its database in
`<base_dir>/<session>/catalog`, and gives its address to any component that
asks for a [`CatalogAddress`][redsun.catalog.CatalogAddress]. It registers
nothing in the catalog itself. Acquisition bytes belong to the service and its
device ([ADR 0013](decisions/0013-acquisition-storage-belongs-to-the-device.md)),
and the session's components decide whether runs are recorded. Each component
opens its own client with `tiled`'s `from_uri` and gets the whole client API.

The server reads `application/x-ome-zarr` files with `ome-tiled`, which serves
an OME-Zarr image as one array whose `dims` are its axis names. The session
also registers `ome-tiled`'s consolidator for `TiledWriter`, so the writer
stores an image with the shape of its store rather than one derived from the
[documents](glossary.md#document).

## One catalog per session

A catalog indexes only the runs of its own session, so to ask a question
across sessions you open each catalog. In exchange, everything a session
produced lives under one directory, which you can archive or delete as a
unit.

## Writing to registered files

Registering a file records where it is, but it doesn't protect the file.
`tiled`'s array write routes, `write`, `write_block` and `patch`, reach a
registered file just as they reach one the catalog created.
`management=external` only records where a file came from, and forbids
nothing. `write_block` is the hardest to notice, because it replaces one chunk
and the rest of the file still reads correctly.

!!! warning "A client can overwrite a registered file"

    `redsun` calls none of these routes, but a component holding a client can.
    A component that writes into the catalog should create its own nodes, as
    `client[run_uid].write_array(...)` does, and leave registered ones alone.
