---
icon: lucide/database
---

# How the session catalog works

A session whose `storage` section has a `catalog` key runs a `tiled` server on
this machine, from build to shutdown.
[Keep a catalog of runs](../how-to/keep-a-catalog.md) shows how to use it.

## What `redsun` does

It starts the server, keeps its database in `<base_dir>/<session>/catalog`,
and gives its address to any component asking for a
[`CatalogAddress`][redsun.catalog.CatalogAddress]. It registers nothing: acquisition bytes belong to the service and its device
([ADR 0013](decisions/0013-acquisition-storage-belongs-to-the-device.md)), and
the session's components decide whether runs are recorded. Each opens its own
client with `tiled`'s `from_uri` and gets the whole client API.

The server reads `application/x-ome-zarr` files with `ome-tiled`, which serves
an OME-Zarr image as one array whose `dims` are its axis names. The session
also registers `ome-tiled`'s consolidator for `TiledWriter`, so the writer
stores an image with its store's shape rather than one derived from the
documents.

## One catalog per session

A catalog indexes only its session's runs; a question across sessions means
opening each catalog. In exchange, everything a session produced lives under
one directory and can be archived or deleted as a unit.

## A registered file can be changed through the catalog

Registering a file records where it is; it does not protect it. `tiled`'s
array write routes, `write`, `write_block` and `patch`, reach a registered
file as they reach one the catalog created. `management=external` records
where a file came from; it forbids nothing. `write_block` is the least
visible: it replaces one chunk and the rest reads correctly.

`redsun` calls none of these routes. A component holding a client can, so one
that writes into the catalog should create its own nodes, as
`client[run_uid].write_array(...)` does, and leave registered ones alone.
