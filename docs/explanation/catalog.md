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
nothing in the catalog itself. Acquisition bytes belong to the service and its device
([ADR 0013](decisions/0013-acquisition-storage-belongs-to-the-device.md)), and
the session's components decide whether runs are recorded. Step through to
see who does what:

```d2 title="A session with a catalog"
...@diagrams/style
label: "A session whose storage section has a catalog key runs a catalog. Its components decide what goes in."
grid-rows: 2
grid-columns: 3
vertical-gap: 80
horizontal-gap: 130
session: "session" {
  class: step
  tooltip: A session whose storage section has a catalog key. Without the tiled extra installed, it refuses to build.
}
server: "tiled server\non this machine" {class: hidden}
database: "catalog database" {class: hidden}
component: "component" {class: hidden}
writer: "TiledWriter\na document callback" {class: hidden}
store: "the camera's store\nOME-Zarr" {class: hidden}
session -> server: "starts" {style.opacity: 0}
server -> database {style.opacity: 0}
session -> component: "CatalogAddress" {style.opacity: 0}
component -> writer: "subscribes" {style.opacity: 0}
writer -> server: "the run's\ndocuments" {style.opacity: 0}
server -> store: "reads" {style.opacity: 0}
steps: {
  1: {
    label: "The session starts a tiled server on this machine in its first build step, with its database in a catalog folder inside the session's folder. It stops the server at shutdown, after every component and service."
    server.class: step
    server.tooltip: The session starts the server in its first build step and stops it at shutdown, after every component and service. A server that fails to start is logged, and the session carries on without it.
    database.class: file
    database.tooltip: The database lives in a folder named catalog, inside the session's folder under the base directory.
    (session -> server)[0].style.opacity: 1
    (server -> database)[0].style.opacity: 1
  }
  2: {
    label: "Any component can ask for a CatalogAddress, and opens its own client with tiled's from_uri."
    component.class: step
    component.tooltip: Any component can ask for a CatalogAddress, and opens its own client with tiled's from_uri, which gives it the whole client API.
    (session -> component)[0].style.opacity: 1
  }
  3: {
    label: "A component that wants runs recorded subscribes a TiledWriter, from bluesky-tiled-plugins, which sends each run's documents to the server."
    writer.class: step
    writer.tooltip: TiledWriter, from bluesky-tiled-plugins, writes a run's documents into the catalog. The component decides whether to subscribe one.
    (component -> writer)[0].style.opacity: 1
    (writer -> server)[0].style.opacity: 1
  }
  4: {
    label: "The server reads the frames from the camera's store, but only from the session's directory and the directories storage.catalog lists under readable."
    store.class: file
    store.tooltip: The server reads files only from the session's directory and the directories storage.catalog lists under readable. It serves an OME-Zarr image as one array whose dims are its axis names.
    (server -> store)[0].style.opacity: 1
  }
}
```

The server reads `application/x-ome-zarr` files with `ome-tiled`, whose
consolidator the session registers for `TiledWriter`. A consolidator turns a
[`StreamResource`](glossary.md#streamresource) and its
[`StreamDatum`](glossary.md#streamdatum) documents into one catalog entry;
this one reads the image's shape, chunks and axis names from its store rather
than from the [documents](glossary.md#document).

## One catalog per session

A catalog indexes only the runs of its own session, so to ask a question
across sessions you open each catalog. In exchange, everything a session
produced lives under one directory, which you can archive or delete as a
unit.

## Writing to registered files

Registering a file doesn't protect it: `tiled`'s `write`, `write_block` and
`patch` reach a registered file like any other, and `management=external`
forbids nothing. `write_block` is the hardest to notice, since it replaces one
chunk and the file still reads correctly.

!!! warning "A client can overwrite a registered file"

    `redsun` calls none of these routes, but a component holding a client can.
    If your component writes into the catalog, have it create its own nodes,
    as `client[run_uid].write_array(...)` does, and leave registered ones
    alone.
