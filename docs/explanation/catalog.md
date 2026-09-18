# The session catalog

A session whose `storage` section has a `catalog` key runs a `tiled` server on
this machine, started when the session is built and stopped when it shuts down.
[Keep a catalog of runs](../how-to/keep-a-catalog.md) shows how to turn it on
and fill it.

## What `redsun` does and does not do

`redsun` starts the server, keeps its database in
`<base_dir>/<session>/catalog`, and provides its address under
[`CATALOG`][redsun.catalog.CATALOG]. It registers nothing: the acquisition's
bytes belong to the service and its device
([ADR 0013](decisions/0013-acquisition-storage-belongs-to-the-device.md)), and
whether a session's runs are recorded is decided by the components it declares.
Components open their own clients with `tiled`'s `from_uri`, so each gets the
whole client API rather than a subset chosen by `redsun`.

The server reads `application/x-ome-zarr` files with `ome-tiled`, which serves
an OME-Zarr image as one array whose `dims` are its axis names. The session
also registers `ome-tiled`'s consolidator for `bluesky-tiled-plugins`'
`TiledWriter`, which makes the writer store an image with the shape its store
holds rather than one derived from the documents.

## One catalog per session

A session's catalog indexes only that session's runs. There is no tree spanning
sessions: a question asked across sessions means opening each one's catalog.
Keeping the catalog inside the session's directory means everything a session
produced can be archived or deleted as a unit.

## A registered file can be changed through the catalog

Registering a file records where it is. It does not protect it. `tiled`'s
array write routes, `write`, `write_block` and `patch`, reach a registered
file as they reach one the catalog created, and `management=external` on a
data source records where the file came from rather than forbidding writes.
`write_block` does the least visible damage: it replaces one chunk and leaves
the rest reading correctly.

`redsun` calls none of those routes. A component holding a client can, so a
component that writes into the catalog should create its own nodes, as
`client[run_uid].write_array(...)` does, and leave registered ones alone.
