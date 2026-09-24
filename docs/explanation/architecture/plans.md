# Plans

`redsun` builds on the [Bluesky plan system](https://blueskyproject.io/bluesky/main/plans.html).
A *plan* is a generator yielding `Msg` objects, which the `RunEngine` turns
into hardware calls.

`redsun` adds two things:

- **`continous` plans** run in a loop, optionally pausable, and accept user
  actions while running.
- **`PlanSpec`** describes a plan's signature, from which the view layer builds
  a parameter form.

---

## Continuous plans

Mark a plan as continuous with the `@continous` decorator:

```python
from redsun.engine.actions import continous, Action
from bluesky.utils import MsgGenerator


@continous(togglable=True, pausable=True)
def live_scan(detectors: Sequence[DetectorProtocol]) -> MsgGenerator[None]:
    while True:
        yield from bps.trigger_and_read(detectors)
```

The decorator sets `__togglable__` and `__pausable__` on the function;
`create_plan_spec` reads them to set up the run and pause buttons.

### In-flight actions

An `Action` is something the user triggers while the plan runs. Declare one
as a parameter default:

```python
from redsun.engine.actions import Action

snap_action = Action(name="snap", description="Capture a single frame")


@continous
def live_view(
    camera: CameraProtocol,
    snap: Action = snap_action,
) -> MsgGenerator[None]:
    while True:
        yield from read_while_waiting([camera], snap_action.event_map)
        yield from bps.trigger_and_read([camera])
```

The view shows `snap` as a button. A click sets the `SRLatch` inside
`snap_action`, which releases `wait_for_actions` inside `read_while_waiting`.

A toggle button is an action with `togglable=True`:

```python
Action(
    name="led",
    description="Toggle illumination",
    togglable=True,
    toggle_states=("On", "Off"),
)
```

### SRLatch

`SRLatch` is the primitive behind `Action`: two `asyncio.Event` objects, with
a wait for either state:

```python
latch = SRLatch()

# in a coroutine:
await latch.wait_for_set()  # blocks until set()
await latch.wait_for_reset()  # blocks until reset()
```

For a `wait_for_actions` message, the `RunEngine` runs one `wait_for_set` (or
`wait_for_reset`) task per latch and returns the first to finish.

---

## Plan specification

`create_plan_spec` inspects a plan's signature and returns a `PlanSpec`:

```python
from redsun.presenter.plan_spec import create_plan_spec

spec = create_plan_spec(my_plan, devices={"stage": motor, "cam": camera})
```

Each parameter becomes a `ParamDescription` with:

| Field | Meaning |
|-------|---------|
| `annotation` | stripped type (no `Annotated` wrapper) |
| `choices` | string labels for `Literal` or device params |
| `multiselect` | True for `Sequence[...]` / `*args` device parameters |
| `device_proto` | the device class or runtime-checkable protocol for device params |
| `actions` | `Action` metadata if the default is an `Action` |

### Annotation dispatch

Annotations map to `ParamDescription` fields, first match wins:

1. `Literal["a", "b"]` -> `choices=["a", "b"]`
2. `Sequence[MyDevice]` -> multi-select, `choices=<matching device names>`
3. `*args: MyDevice` (VAR_POSITIONAL) -> multi-select
4. `MyDevice` (bare protocol) -> single-select
5. Everything else -> a plain value, left to the view layer to render

Step 5 accepts:

- `int`, `float`, `str`, `bool`, `bytes` and `range`
- `Path`
- `datetime`, `date`, `time` and `timedelta`
- any `Enum` subclass
- a sequence of anything that is not a device

A *required* parameter with any other annotation raises
`UnresolvableAnnotationError`, and the plan is skipped instead of shown with a
control nobody can fill in. `Any` is excluded on purpose: it would accept
everything and show as a bare text field.

The check is plain Python and imports no toolkit, so a plan can be inspected
before any application object exists. The view layer turns descriptions into
widgets; for Qt, see [Qt widgets - plans](qt-widgets.md).

### Collecting and resolving arguments

Once the user fills in the form, the presenter turns the values into a plan
call:

```python
from redsun.presenter.plan_spec import collect_arguments, resolve_arguments

# 1. Resolve: string device names -> live device instances
resolved = resolve_arguments(spec, widget_values, devices)

# 2. Collect: build (args, kwargs) matching the plan signature
args, kwargs = collect_arguments(spec, resolved)

# 3. Run
engine(my_plan(*args, **kwargs))
```

---

## Plan stubs

`redsun.engine.plan_stubs` holds stubs to use inside larger plans.

### Action flow-control stubs

```python
import redsun.engine.plan_stubs as rps

# block until any latch in the map changes state, polling at `timeout`
name, latch = yield from rps.wait_for_actions(action.event_map, timeout=0.016)
```

### Descriptor stubs

```python
import redsun.engine.plan_stubs as rps

# gather descriptors from Readable / Collectable devices inside a plan
descriptor = yield from rps.describe(readable)
descriptors = yield from rps.describe_collect(collectable)
```

### Lock stubs

A plan locks the devices it must not have disturbed, and views disable their
controls while those devices are locked. The run engine keeps the locks and
announces them on `RunEngine.sig_locks_changed`, which a view connects to.

```python
import redsun.engine.plan_stubs as rps

# lock the stage and camera while the inner plan runs, however it ends
yield from rps.lock_wrapper(scan(stage, camera), stage, camera)
```

---

## See also

- [`engine/actions` API](../../reference/api/engine.md#actions)
- [`engine/plan_stubs` API](../../reference/api/engine.md#plan-stubs)
- [`presenter/plan_spec` API](../../reference/api/presenter.md#plan-specification)
- [Qt widgets - plans](qt-widgets.md)
