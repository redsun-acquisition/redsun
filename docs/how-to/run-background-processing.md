---
icon: lucide/cpu
---

# How to run background processing

A component that computes something slow, such as the median of every frame of
a scan, can hand the work to the session's threads. The window and the run's
other callbacks keep going while the work runs, and the result comes back to
the component when it is ready. You ask the session for an
[executor](../explanation/glossary.md#executor), submit a function to it, and
take the result with `then`.
[How background computation works](../explanation/background-computation.md)
explains what the session does behind the executor.

## Prerequisites

You need a session and a [presenter](../explanation/glossary.md#presenter)
that receives the [documents](../explanation/glossary.md#document) of a
[run](../explanation/glossary.md#run). The blocks below are parts of one
script, and the whole script is at the end.

## Write the function

Put the work in a function that takes everything it needs as arguments and
returns its result:

```{.python}
--8<-- "docs/examples/background_processing.py:function"
```

The function reads nothing from the component, so it can run on any thread
while the component goes on receiving documents. A thread helps only when the
function spends its time in code that lets other threads run meanwhile, as
`numpy` does in `np.median`. Code written in plain Python takes turns with
every other thread, the window's included, so it runs no faster on a thread
and slows the window down while it runs.

## Ask for an executor

Annotate a constructor parameter with
[`ThreadExecutor`][redsun.compute.ThreadExecutor]:

```{.python}
--8<-- "docs/examples/background_processing.py:presenter"
```

The session gives the presenter an executor of its own, over the thread
[pool](../explanation/glossary.md#pool) every component shares. The executor
is named after the component, its [owner](../explanation/glossary.md#owner),
so every count and log line about its calls says who made them. When the
session shuts the presenter down, it shuts the executor down too, so you
write no cleanup for it.

A `setup` method can ask for a `ThreadExecutor` with the same annotation, and
receives the object the constructor received. A component that asks for the
pool itself, `ThreadPool`, is skipped with a message naming the executor to
ask for instead.

## Submit the work

Call `submit` with the function and its arguments, and pass `then` what to do
with the result:

```{.python}
--8<-- "docs/examples/background_processing.py:documents"
```

`submit` returns at once with a [`Future`][redsun.compute.Future], so `stop`
returns while the median is still running. When the call finishes, `then`
hands its result to the first callback, here the signal's `emit`, or the
exception it raised to the second. Without a second callback, a failure is
logged with the name of the first one.

In a Qt session the callback runs on the main thread, so it may touch a
widget. A callback marked with `@slot(thread=...)` runs on the thread the
marker names instead, where `"current"` stands for the thread the session was
built on. In a session whose frontend names no thread for results, such as
one without a GUI, the callback runs on the thread that finished the call;
[`Frontend.results_thread`][redsun.Frontend.results_thread] is where a
frontend names it.

A result that arrives after the session has shut its component down is
dropped and never reaches the callback.

A coroutine slot can await the result instead:

```python
median = await self._executor.run(median_of, frames)
```

Some libraries start threads of their own, which the session cannot limit,
and take the number to start as an argument, such as `workers=` in
`scipy.fft`. Pass them `self._executor.native_threads`, the number the session
chose for each call.

## Show the result in a view

The presenter publishes the median on a signal, so a view shows it in a
[slot](../explanation/glossary.md#slot):

```{.python}
--8<-- "docs/examples/background_processing.py:view"
```

Link the two in the session:

```{.python}
--8<-- "docs/examples/background_processing.py:session"
```

## Warm up from `setup`

The first call of a function is often slower than the next ones, because a
library loads or prepares something on first use. Submit a small call from
`setup`, so that cost is paid before the first run:

```{.python}
--8<-- "docs/examples/background_processing.py:setup"
```

The session starts its pools only after every component's
[`setup`](../explanation/glossary.md#setup) has returned. So a call submitted
from `setup` waits in the pool, and runs first when the pool starts.

!!! warning "`setup` cannot wait for its own calls"

    A call submitted from `setup` cannot finish before `setup` returns, so
    waiting for it there would wait forever. `result()` and `exception()`
    without a timeout refuse to wait and raise `RuntimeError: the pool starts
    after every setup; use .then(...)`, and the build logs that the component
    could not be set up. `concurrent.futures.wait` and `as_completed` don't
    raise; they hang the build. Take the result with `then` instead.

## Choose how the cores are split

The session decides how many threads the pool has and how many threads each
call's native libraries may use. A word in the
[session file](../explanation/glossary.md#session-file) picks the split:

```yaml
compute: latency
```

`latency` gives one call all the cores, `throughput` runs as many calls at
once as there are cores, and `balanced`, the default, sits between the two.
[Compute](../reference/session-file.md#compute) lists every key of the
section. The build's summary names what the session chose, and
[`Session.pool_settings`][redsun.Session.pool_settings] returns the same
numbers:

```text
Compute: 15 cores, preset balanced
ThreadPool: 3 threads, 5 native threads each
```

## Read what the pool did

[`usage`][redsun.compute.ThreadExecutor.usage] returns the counts of the
component's own calls: waiting, running, completed and failed, and the
longest any call waited for a free thread. The session also logs what each
pool did when it shuts down:

```text
thread pool: 3 workers, 214 calls (median 214), 2 failed, longest idle 1.4 s
```

A call that waited more than a second for a free thread is logged when it
starts, under the logger `redsun.compute.<owner>`. A thread the session
keeps for this wakes every 50 ms. If it wakes more than 0.2 s late, something
held every other thread back, so the session logs the name of each function
the pool was running at that moment, once per function.

## Test the component

Load the `redsun.testing` fixtures as
[How to test a plugin](test-a-plugin.md#load-them) shows, and pass the
component the `inline_threads` fixture:

```{.python}
--8<-- "tests/test_doc_examples.py:test"
```

[`inline_threads`][redsun.testing.inline_threads] is a `ThreadExecutor` over
a pool with no threads, already started. Each call runs in the test's own
thread before `submit` returns, and `then` hands its result over at once, so
the test can check it on the next line.

## Leave the window's teardown alone

!!! warning "Work started while the window closes fails"

    By the time Qt tears the window down and calls `closeEvent`, the session
    has shut down its executors and pools and closed the values it hands to
    components. A `submit` there raises `RuntimeError: cannot schedule new
    futures after shutdown`, and a command raises `RuntimeError: the registry
    is closed`. A call submitted from a component's own `shutdown` is
    cancelled right after it. Start the work while the session runs, from a
    document, a signal or a user's action.

## The example in full

??? example "The whole script"

    ```{.python}
    --8<-- "docs/examples/background_processing.py"
    ```
