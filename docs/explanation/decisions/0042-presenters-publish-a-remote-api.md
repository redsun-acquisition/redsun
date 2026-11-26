# 42. Presenters publish a remote API

Date: 2026-11-24

## Status

Accepted

## Context

A session shown in a Qt window can be used only at the computer running it.
To move a stage from a browser, or from a script on another computer, the
session has to answer requests over the network, and writing one route by
hand for every command a presenter offers would repeat each presenter's slots
in a second place that drifts from the first.

The presenters already hold what a client needs. Their
[slots](../glossary.md#slot) are the commands a view sends, their properties
the state a view reads when it is set up, and their
[signals](../glossary.md#signal) report every change. An API at the level of
presenters therefore reuses them as they are, while an API at the level of
devices would skip the presenters' checks, such as the refusal to move a
device a plan holds.

Not every slot is safe to call from outside the process, though. The built-in
positioner has a slot through which the acquisition presenter tells it which
devices a running plan holds:

```python
class PositionerPresenter:
    @slot(signal="sig_locks_changed")
    def set_locked(self, names: frozenset[str]) -> None: ...
```

A browser calling it could unlock a stage in the middle of a plan, so
publishing every slot is ruled out, and the presenter's author has to say
which members a client may use.

## Decision

**A presenter member marked with `redsun.remote` is published, and nothing
else is.** The mark sits directly on the `def`, under `@slot` for a command
and under `@property` for state:

```python
class MyController:
    sig_moved = Signal(str, float)

    @property
    @remote
    def names(self) -> list[str]: ...

    @slot
    @remote
    async def move_to(self, motor: str, position: float) -> float: ...
```

A web session gives each remote slot a `POST` route and each remote property
a `GET` route, both under `/api/{presenter}/`, and a presenter with no remote
member is not served at all.

### How a member is marked

Four ways of marking were weighed.

A keyword on `slot`, `@slot(remote=True)`, would keep commands in one
decorator, but state is a property, not a slot, so it would need a second mark
of its own:

```python
@slot(remote=True)
async def move_to(self, motor: str, position: float) -> float: ...

@property  # no way to say "remote" here
def names(self) -> list[str]: ...
```

`remote` alone, on a method that is not a slot, would give the method a route
under its attribute name, while a session file's wiring names it by its port
name, which `@slot(name=...)` may change. One method would then have two
public names, so a remote method must also be a slot. The web session finds
commands with `ports()`, as the wiring does, and names each route after the
port:

```python
@slot(name="goto")
@remote
async def move_to(self, motor: str, position: float) -> float: ...
# served as POST /api/ctrl/goto, and named ctrl.goto in a session file's wiring
```

Placing `remote` above `@slot` or `@property` would mark the object they
return, not the function. A subclass of `property` that carried the mark was
tried and dropped, because `mypy` in strict mode types the value of such a
property as `Any`. So `remote` takes the plain function and returns it
unchanged, which keeps every type, and it raises a `TypeError` naming the
function when it is given anything else, including a function `@slot` has
already marked:

```python
@remote  # TypeError: @remote is above @slot: put it below, directly on the def
@slot
async def move_to(self, motor: str, position: float) -> float: ...
```

The fourth option, marking signals one by one with `remote(Signal(...))`, was
weighed against publishing them all. A signal only reports what happened, so a
client following it changes nothing, and a client calling a command needs the
events that command causes. **Every public signal of a served presenter is
therefore published, with no mark,** on the WebSocket `/api/events`.

### Async slots and sync getters

**A remote slot is an `async def`, and a remote property's getter is a plain
`def`.** The session runs a remote slot on its event loop, and a slot that
blocks there would stop every other route. A property is read by
`property.__get__`, which returns what the getter returns, so an `async`
getter hands back a coroutine nobody awaits; a Qt view reading the same
property in its plain `setup` would get the coroutine too. State that needs
I/O to read is published as an `async` remote slot returning it:

```python
@slot
@remote
async def position(self, motor: str) -> float:
    return await self.motors[motor].position.get_value()
```

An `async` slot may now return a value, which becomes the answer to the
request. A signal connected to the slot drops it, so a remote slot that
returns a value can still be linked in `wire()`. A plain `def` slot still
returns nothing.

Every route the session builds is an `async def` endpoint, the one reading a
property included. `fastapi` runs an endpoint written as a plain `def` on a
thread of its own, which would read a presenter's state while the presenter's
coroutines change it on the loop.

These rules hold for any frontend serving a presenter, so `remote` and the
code reading a presenter's remote members check them. Only the `fastapi`
frontend needs each type to have a JSON Schema, so it checks every parameter
and return type of a remote member, and every argument type of a published
signal, when it builds the API. A presenter breaking a rule, or naming a
type with no JSON Schema, is left out of the API with a log line naming the
member, and it is still built and still runs.

### Views keep sync slots

Views have the opposite rule, because a Qt view's slots run on the GUI
thread, where an `async` slot cannot run. **A frontend refuses a view
declaring an `async` slot unless it sets `Frontend.async_view_slots`.** No
frontend `redsun` ships sets it. Before, the declaration was accepted, and the
slot ran as a coroutine on the session's loop, off the GUI thread:

```python
# before: accepted, then touched the widget from the wrong thread
class MyView(QWidget):
    @slot
    async def show_position(self, position: float) -> None:
        self.label.setText(str(position))
```

After, the view is refused at declaration and skipped, with a log line naming
the slot. The fix is a plain `def`:

```python
# after
class MyView(QWidget):
    @slot
    def show_position(self, position: float) -> None:
        self.label.setText(str(position))
```

### One frontend per session

A web session is a session class of its own,
`redsun.fastapi.FastAPISession`, registered as the `fastapi` frontend, and it
has no views. A process runs one frontend, so
an application that wants a window and a web API declares its components once
and builds each frontend's session on top, the frontend's class first:

```python
class MyCore(Session):
    stage: AsDevice[MyMotor]
    ctrl: AsPresenter[MyController]


class OnWeb(FastAPISession, MyCore):
    pass


class OnDesktop(QtSession, MyCore):
    panel: AsView[MyView]
```

A session file's sections belong to their frontend in the same way. The
`remote` section, which says where the API listens, is refused by a session
that does not serve one, and a web session refuses `views`, `layout`,
`shortcuts`, `actions` and `color_scheme`. `Frontend.foreign_sections` lists
what each frontend refuses, and `layout` is refused by every frontend that
lays out no window.

## Consequences

- A presenter author decides what a client may call by marking it, and a
  slot left unmarked is reachable only through wiring in the process.
- The API carries the types of the annotations: `fastapi` checks each request
  body and answers a wrong type with 422 before the slot runs, and its OpenAPI
  document is what a TypeScript client is generated from. A remote member's
  annotations must resolve at runtime, so the imports they need stay outside
  `if TYPE_CHECKING:`.
- OpenAPI cannot describe the messages of a WebSocket, so the session
  describes them in an AsyncAPI 3.0.0 document at `GET /asyncapi.json`, with
  one message per published signal.
- The API has no authentication. A session listening on an address other
  computers reach lets each of them call every remote slot.
- The positioner and light presenters mark their state and their moves and
  light controls. Their `set_locked` and `configure` slots stay unmarked.
- The acquisition presenter is not served, because its plans have no JSON
  form yet.
