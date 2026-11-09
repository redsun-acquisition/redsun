---
icon: lucide/cpu
---

# How to run background processing

A component that computes something heavy, such as the median of every frame of
a scan, can hand that work to the session's threads and get the result back
later, so the window and the run's other [callbacks](../explanation/glossary.md#callback)
go on while it computes. You ask for an
[executor](../explanation/glossary.md#executor) in the component's constructor,
send the work to it, and say where the result goes.
[Background computation](../explanation/background-computation.md) explains
how the session shares its cores between components.

## Prerequisites

You need a [presenter](../explanation/glossary.md#presenter) or a
[view](../explanation/glossary.md#view), and a function doing the heavy work.
The work should spend its time in `numpy` or another library that runs native
code, because only native code runs on several threads at once; the
[threads and the GIL](../explanation/background-computation.md#threads-and-the-gil)
section says how to tell. The blocks below are parts of one script, and the
whole script is at the end.

## Write the work as a function

Put the heavy step in a function of its own, at module level, that takes
everything it needs as arguments:

```{.python}
--8<-- "docs/examples/background_median.py:median"
```

The function runs on another thread, so it shouldn't touch the component or a
widget. Let it read its arguments and return a result.

## Ask for an executor

Annotate a constructor parameter with
[`ThreadExecutor`][redsun.compute.ThreadExecutor]. The session sees the
annotation and passes the component an executor of its own:

```{.python}
--8<-- "docs/examples/background_median.py:presenter"
```

`MedianPresenter` is a `DocumentRouter`, so the session sends it the documents
of every run. It collects the frames of the data key it was given as `source`,
and when the run stops it sends `median_of` to the executor and returns at
once.

!!! warning "An executor asked for in `setup`"

    The session gives executors only to the constructor. A `setup` method or a
    provider that asks for one stops the build with a `TypeError`, and so does
    a session file that fills the parameter with a value. Take the executor as a
    constructor parameter.

Don't build an executor yourself inside the component. `ThreadExecutor(2)`
makes a pool of its own, which the session neither sizes nor stops, so it can
take cores the session has given to other work.

## Get the result back

[`deliver`][redsun.compute.deliver] takes the future that `submit` returned
and the method that should receive the result:

```{.python}
--8<-- "docs/examples/background_median.py:documents"
```

When the median is ready, `deliver` calls `_publish` with it on the main
thread, the thread the window runs on, so `_publish` can emit a signal that a
widget is connected to. A method marked with
[`@slot(thread=...)`](wire-components.md) receives it on the thread it names
instead. If the computation raises, `deliver` logs the exception and doesn't
call the method.

!!! warning "A list you keep filling after `submit`"

    The function receives the list itself, not a copy. If `event` went on
    appending to that list while the median runs, the median would read a
    list that changes under it. Start a new list for each run, as `start`
    does here, so the list sent at `stop` is never touched again.

## Await the result in an `async` slot

An `async` [slot](../explanation/glossary.md#slot) can await
[`run`][redsun.compute.ThreadExecutor.run] instead, which takes the same
arguments as `submit`:

```{.python}
--8<-- "docs/examples/background_median.py:recompute"
```

The slot waits for the result without holding the loop it runs on, and the
code after `await` runs where the slot runs.

## Choose how the session spends its cores

Set `compute` on the session class to pick a preset:

```{.python}
--8<-- "docs/examples/background_median.py:session"
```

| Preset | Pool threads | Native threads per pool thread |
| --- | --- | --- |
| `latency` | 1 | every core of the budget |
| `balanced` | a quarter of the budget's cores, at least 2 | the budget's cores divided by the pool threads |
| `throughput` | one per core of the budget | 1 |

Pick `latency` when one computation at a time should finish as fast as
possible, `throughput` when many independent ones run together, and keep the
default, `balanced`, when you don't know. A session file overrides the class
key by key:

```yaml
compute:
  preset: throughput
  cores: 8
```

[Session file](../reference/session-file.md#compute) lists every key. The
session writes what it chose into its build summary, in a line such as
`compute: balanced, 15 cores, 3 threads x 5 native`.

## Test the component

Ask for the [`inline_threads`][redsun.testing.inline_threads] fixture and pass
it to the component yourself. Its calls run as soon as they are submitted, so
the result is there when the method that submitted them returns:

```{.python}
--8<-- "docs/examples/background_median_tests.py:test"
```

With no Qt session running, `deliver` calls `_publish` at once on the thread
that finished the call, which here is the test's own.

## The example in full

??? example "The whole script"

    ```{.python}
    --8<-- "docs/examples/background_median.py"
    ```

??? example "The test"

    ```{.python}
    --8<-- "docs/examples/background_median_tests.py"
    ```
