# Plans

Redsun builds on the [Bluesky plan system](https://blueskyproject.io/bluesky/main/plans.html).
A *plan* is a generator function that yields `Msg` objects; the `RunEngine`
consumes them and drives hardware.

Redsun adds two layers on top:

- **`continous` plans** - plans that run in a loop, with optional pause/resume
  and in-flight user actions.
- **`PlanSpec`** - a structured description of a plan's signature, used by the
  view layer to build a parameter form automatically.

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

The decorator stamps `__togglable__` and `__pausable__` onto the function.
`create_plan_spec` reads these to configure the run/pause buttons in the UI.

### In-flight actions

An `Action` is a user-triggered side effect that can fire while the plan runs.
Declare one as a parameter default:

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

The view renders `snap` as a button. When clicked, the `SRLatch` inside
`snap_action` is set, unblocking `wait_for_actions` inside `read_while_waiting`.

Togglable actions (represented as toggle buttons) use `togglable=True`:

```python
Action(
    name="led",
    description="Toggle illumination",
    togglable=True,
    toggle_states=("On", "Off"),
)
```

### SRLatch

`SRLatch` is the synchronisation primitive behind `Action`. It wraps two
`asyncio.Event` objects and supports waiting for either state:

```python
latch = SRLatch()

# in a coroutine:
await latch.wait_for_set()  # blocks until set()
await latch.wait_for_reset()  # blocks until reset()
```

The `RunEngine` handles `wait_for_actions` messages by running one
`wait_for_set` (or `wait_for_reset`) task per latch and returning the first
that completes.

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

The dispatch is table-driven. Annotations are mapped to `ParamDescription`
fields in this priority order:

1. `Literal["a", "b"]` → `choices=["a", "b"]`
2. `Sequence[MyDevice]` → multi-select, `choices=<matching device names>`
3. `*args: MyDevice` (VAR_POSITIONAL) → multi-select
4. `MyDevice` (bare protocol) → single-select
5. Everything else → delegated to magicgui

Plans with required parameters that fall through to step 5 and are not
magicgui-resolvable raise `UnresolvableAnnotationError` and are skipped.

### Collecting and resolving arguments

Once the user fills in the form, the presenter calls two functions to
turn widget values into a plan call:

```python
from redsun.presenter.plan_spec import collect_arguments, resolve_arguments

# 1. Resolve: string device names → live device instances
resolved = resolve_arguments(spec, widget_values, devices)

# 2. Collect: build (args, kwargs) matching the plan signature
args, kwargs = collect_arguments(spec, resolved)

# 3. Run
engine(my_plan(*args, **kwargs))
```

---

## Plan stubs

`redsun.engine.plan_stubs` provides stubs that compose inside larger plans.

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

---

## See also

- [`engine/actions` API](../../reference/api/engine.md#actions)
- [`engine/plan_stubs` API](../../reference/api/engine.md#plan-stubs)
- [`presenter/plan_spec` API](../../reference/api/presenter.md#plan-specification)
- [Qt widgets - plans](qt-widgets.md)
