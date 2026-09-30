---
icon: lucide/code
---

# redsun.engine

## Run engine

::: redsun.engine
    options:
      members:
        - RunEngine
        - Deferrals
        - PlanProgress
        - ProgressState
        - register_bound_command

`RunEngineResult` is the class of `bluesky`,
[`RunEngineResult`][bluesky.run_engine.RunEngineResult].

## Actions

::: redsun.engine.actions
    options:
      members:
        - continuous
        - PlanAction
        - ActionManager
        - ActionState
        - SRLatch
        - Continuous

### Waiting on a latch

`ActionManager` makes one `SRLatch` for each action it offers, and waits on it. A
latch is set and reset from any thread, and a coroutine waits for either
state on whatever loop it runs:

```python
latch = SRLatch()

# in a coroutine:
await latch.wait_for_set()  # blocks until set()
await latch.wait_for_reset()  # blocks until reset()
```

`latch.changed_at` is when the latch last changed state, as `time.monotonic`
reads it, and `0.0` for a latch that never changed.

For a `wait_for_actions` message, the `RunEngine` runs one `wait_for_set` (or
`wait_for_reset`) task per latch, for `poll_interval` seconds at most. Of
several latches in the wanted state, it returns the one that reached that
state first. Of those that reached it together, it returns the first in the
map. If no latch is in the wanted state when the interval ends, the stub
yields its next checkpoint and sends the message again.

## Plan stubs

`redsun.engine.plan_stubs` holds steps to use inside larger plans, beside those
of `bluesky.plan_stubs`.

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

### Action flow-control stubs

`wait_for_actions` waits on a map of names to latches. `ActionManager.wait` and
`ActionManager.wait_released` use it, so a plan written against an `ActionManager` does
not call it.

```python
import redsun.engine.plan_stubs as rps
from redsun.engine.actions import SRLatch

latches = {"snap": SRLatch()}

# wait until a latch in the map is set, however long that takes,
# with a checkpoint every `poll_interval` seconds
name, latch = yield from rps.wait_for_actions(latches, poll_interval=0.016)
```

The stub does not time out. It waits as long as it takes for a latch to be
set, or reset with `wait_for="reset"`, and returns at once if one already is.
While it waits it yields a checkpoint every `poll_interval` seconds, 1/60 s by
default. A checkpoint is where the plan can be paused, so the stub cannot sit
between `create` and `save`. An empty map raises `ValueError`.

### Progress stubs

A plan opens a progress scope, moves it and finishes it. The run engine
announces every open scope on `RunEngine.sig_progress`, which a view connects
to. [How to show a plan's progress](../../how-to/show-plan-progress.md) shows
the whole path.

```python
import redsun.engine.plan_stubs as rps

yield from rps.declare_progress("series")
yield from rps.update_progress("series", current=3, initial=0, target=10, unit="frames")
yield from rps.update_progress("series", done=True)
yield from rps.monitor_progress("frames", status)  # follow a device status
```


::: redsun.engine.plan_stubs
    options:
      members:
        - wait_for_actions
        - describe
        - describe_collect
        - lock
        - unlock
        - lock_wrapper
        - declare_progress
        - update_progress
        - monitor_progress
