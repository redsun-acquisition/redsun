---
icon: lucide/globe
---

# How to serve a session over the web

A [web session](../explanation/glossary.md#web-session) publishes your
presenters as an HTTP API, so a page in a browser, a script or any other HTTP
client can call their slots, read their state and follow their signals. You
mark the members a client may use, and the session writes every route from
them.
[ADR 42](../explanation/decisions/0042-presenters-publish-a-remote-api.md)
explains the design.

## Prerequisites

You need the `fastapi` extra, which installs `fastapi` and `uvicorn`:

```bash
pip install "redsun[fastapi]"
```

The Python blocks below are parts of one script, and the whole script is at
the end.

## Declare the components in a base class

A web session has no views, so it declares its devices and presenters like a
[headless session](run-without-a-gui.md). Put them in a class of their own,
built on [`Session`][redsun.Session]:

```{.python}
--8<-- "docs/examples/web_session.py:core"
```

The web session then subclasses it, with the frontend's class first:

```{.python}
--8<-- "docs/examples/web_session.py:session"
```

Because the components live in `MyCore`, a desktop session can share them:
`class MyWindow(QtSession, MyCore)` adds the views and opens a window. One
process runs one frontend, so you start the web session and the desktop
session as two separate programs.

## Mark what a client may use

A presenter is served only when at least one of its members carries
[`remote`][redsun.remote]. Write the mark directly on the `def`, under `@slot`
for a command and under `@property` for state:

```{.python}
--8<-- "docs/examples/web_session.py:controller"
```

A remote slot is an `async def`, because the session runs it on its event
loop, and it may return a value, which becomes the answer to the request. A
remote property's getter is a plain `def`. Its value has to be ready without
waiting, so state that takes I/O to read is published as an `async` remote
slot returning it.

A slot without the mark stays a slot: you can still link it in `wire()`, but
no client can call it. The mark therefore says what is safe to call from
outside the process, so leave unmarked a slot such as one that unlocks a device
a plan holds.

Every public [signal](../explanation/glossary.md#signal) of a served
presenter is published, with no mark of its own, so `sig_moved` reaches every
client following the session's events.

!!! warning "A presenter breaking a rule is left out of the API"

    The session checks each served presenter when it builds the API. A remote
    slot that is a plain `def`, a remote property whose getter is `async`, an
    annotation that does not resolve at runtime, or a type with no JSON Schema,
    such as an arbitrary class, leaves the presenter out. The presenter is
    still built and runs, and the build's summary lists it under "Not served".
    A [strict session](../explanation/glossary.md#strict-session) stops the
    build instead. Check the log line naming the member, then fix the member
    or drop its mark.

The annotations are read at runtime, because they become the types of the
routes. An import that only an annotation needs therefore stays outside
`if TYPE_CHECKING:`. If your project uses `ruff`'s `TC` rules, add
`redsun.remote` to `runtime-evaluated-decorators`, so `ruff` stops asking you
to move such an import.

## Find the routes

Each marked member gets a route under `/api`, named after the presenter and
the member:

| Member | Route | Body | Answer |
| --- | --- | --- | --- |
| remote slot | `POST /api/{presenter}/{port}` | an object with the slot's parameters | the slot's return value, `null` for `None` |
| remote property | `GET /api/{presenter}/{name}` | none | the property's value |
| every public signal | the WebSocket `/api/events` | none | one message per emission: `{"presenter", "signal", "args"}` |
| the event messages | `GET /asyncapi.json` | none | the AsyncAPI document of `/api/events`: one message per signal, with the JSON Schema of its arguments |

For the script above, `POST /api/ctrl/move_to` with the body
`{"motor": "stage", "position": 2.5}` moves the stage and answers `2.5`, and
`GET /api/ctrl/names` answers `["stage"]`. The body may leave out a
parameter that has a default, and a slot without parameters takes no body. A
body with a wrong type is answered with 422 before the slot runs. A slot that
raises answers 500 with `{"error": "..."}`, and the session logs the
exception.

## Serve the session

Call `serve()`. It builds the session, starts serving, and blocks until you
press Ctrl+C, which stops the server and shuts the session down:

```python
MyApp().serve()
```

The session listens on `127.0.0.1:8000` unless you say otherwise. Open
`http://127.0.0.1:8000/docs` in a browser to see every route with its types,
and to call each one by hand.

## Choose where it listens

The `remote` attribute of the session class gives the defaults, and the
`remote` section of a [session file](../explanation/glossary.md#session-file)
replaces them key by key:

```yaml
remote:
  host: 0.0.0.0
  port: 8080
  origins: ["http://localhost:5173"]
```

`origins` lists the addresses of the pages allowed to call the API from a
browser. A page served from another address, such as a development server on
port 5173, needs its address here; the default, an empty list, allows none.

!!! warning "Anyone who reaches the port can move your devices"

    The API has no sign-in. With `host: 0.0.0.0` every computer that can reach
    the port can call each remote slot, so open it only on a network you
    trust, and keep `127.0.0.1` otherwise.

A session file can describe a web session alone, with `frontend: fastapi` and
no class of your own. [Session file](../reference/session-file.md#remote)
lists the keys, and the sections a web session refuses.

## Try it on the example session

The example session that `redsun` ships serves its positioner and lights the
same way:

```bash
redsun --example --web
```

Its devices are simulated, so nothing outside the process moves.
`http://127.0.0.1:8000/docs` lists the routes, and
[the `redsun` command](../reference/command-line.md) describes the option.

## Generate a TypeScript client

`fastapi` publishes the session's API as an OpenAPI document, at
`/openapi.json`, with the operation ids `{presenter}__{port}` for a slot and
`get_{presenter}__{name}` for a property. `openapi-typescript` turns that
document into types, while the session is serving:

```bash
npx openapi-typescript http://127.0.0.1:8000/openapi.json -o src/api.d.ts
```

A client written against those types fails to compile when a route changes
its name or the type of a parameter. OpenAPI cannot describe the messages of
a WebSocket, so the session describes them at `GET /asyncapi.json` in an
AsyncAPI document, the counterpart of OpenAPI for APIs that send messages:
one message per signal, with the JSON Schema of its arguments.
`@asyncapi/modelina` turns that document into a TypeScript union with one
interface per message, so a client handling the events fails to compile when
a signal changes its name or its arguments. The `redsun` repository holds a
client of the example session in `clients/typescript/`, whose
`npm run generate` builds both sets of types from the documents the
repository's `scripts/export_openapi.py` writes.

## The example in full

??? example "The whole script"

    ```{.python}
    --8<-- "docs/examples/web_session.py"
    ```
