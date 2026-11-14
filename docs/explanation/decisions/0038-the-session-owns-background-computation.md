# 38. The session owns background computation

Date: 2026-11-10

## Status

Accepted

## Context

Components need to run slow work, such as the median of a scan's frames, off
the thread that handed them their data. Each component could start threads of
its own, but none of them knows how many cores the computer has, what the
other components run at the same time, or how many threads `numpy`'s BLAS
library started when it loaded. Two components each starting a thread per
core, each thread calling a library that starts a thread per core, ask for
far more threads than the computer has.

The session knows all of that, and it already hands components what they ask
for in their constructor. So the question was how a component asks for
threads, and how the objects behind that request are split between what the
session holds and what the component holds.

Asking could happen through a decorator on the methods to run in the
background, or through a constructor parameter, the way a component asks for
`SessionConfig`. A decorator hides where a call goes and when its result
comes back, and gives the component no object to cancel a call or read
counts from, so the parameter was chosen:

```python
class MedianPresenter:
    def __init__(self, name: str, executor: ThreadExecutor) -> None:
        self._executor = executor

    def stop(self, doc: RunStop) -> RunStop:
        self._executor.submit(median_of, self._frames).then(self.sig_median.emit)
        return doc
```

What the parameter receives was decided between two designs. In the first,
one class builds its own threads, and the session reaches a second
constructor, private, to hand components a class sharing threads it built:

```python
executor = ThreadExecutor(threads=2)                     # a script
executor = ThreadExecutor._from_pool(shared, "median")   # the session
executor.shutdown()                                      # stops what, for whom?
```

In the second, a pool owns the threads and an executor holds one owner's
calls on a pool:

```python
with ThreadPool(2) as pool:                  # a script builds and starts a pool
    executor = ThreadExecutor(pool, "median")
    ...
    executor.shutdown()                      # this owner's calls only
```

`shutdown` decided between them. In the first design it would have stopped
the threads of every component for an executor the session made, and only a
script's threads for one the script made, so one method would mean two
things depending on how the object was built. In the second, each class has
one `shutdown` with one meaning.

The executor could also have been a protocol, as presenters and views are
([ADR 3](0003-structural-subtyping-for-presenters-and-views.md)). The session
answers a parameter annotated with a protocol by the component whose shape
matches it ([ADR 17](0017-questions-read-from-the-annotation.md)), so an
executor protocol would have been answered with a component, and two
executor protocols with the same members could not be told apart. A class is
looked up by its exact key.

Code that holds the GIL needs worker processes rather than threads, and two
choices came with them. The first was whether every component shares one
process pool, as it shares the thread pool. A worker process that dies takes
the calls it held with it, and the standard library's `ProcessPoolExecutor`
then fails every unfinished call of the pool without saying which call killed
the worker. With one shared pool, the crash of one component's call fails the
calls of every other component, and one component's long queue delays them
all:

```python
class FitPresenter:
    def __init__(self, name: str, executor: ProcessExecutor) -> None: ...

class MedianPresenter:
    def __init__(self, name: str, executor: ProcessExecutor) -> None: ...

# shared pool: a crash in a fit fails the median that waited behind it
# one pool each: the median's pool never sees the fit's workers
```

So each component asking for a `ProcessExecutor` gets a pool of its own, and
the session splits the compute cores between the pools.

The second was whether to start the workers as `redsun`'s own processes,
with their own protocol for sending calls and data, or to hold a standard
`ProcessPoolExecutor`. Workers of our own could resend the lost call of a
crashed worker and move large arrays through rings of shared memory, but
they put a process protocol, its readiness check and its crash handling into
`redsun`. The standard pool already starts and feeds workers, so
`ProcessPool` holds one, started with `spawn`:

```python
with ProcessPool(2) as pool:
    executor = ProcessExecutor(pool, "fit")
    executor.submit(fit_stack, name, shape, dtype).then(show, report)
```

A component that sends large arrays writes them into a block of shared
memory it owns and sends the block's name, so the pool needs no data path of
its own.

## Decision

- A component gets an executor by annotating a constructor parameter with
  its class, and calls `submit` on it from its own code.
- Pools and executors are separate public classes in `redsun.compute`. A
  pool owns its workers, its size, its start and its stop. An executor holds
  one owner's calls on a pool.
- Executors subclass `concurrent.futures.Executor` and keep its `shutdown`
  contract, scoped to their owner's calls: `submit` raises after it, waiting
  calls can be cancelled, running calls finish.
- Executors are concrete `@final` classes, looked up by exact class. A
  private generic base, `PoolExecutor[PoolT]`, reads the pool class from its
  type argument, so the session needs no table from executors to pools.
- Pools share a private base class, `Pool`, holding the start, the calls
  waiting for it, the counts and the shutdown. Each kind writes `_start`,
  `_dispatch` and `_stop`. `ThreadPool` holds a `ThreadPoolExecutor` rather
  than subclassing it, since both would define `submit` and `shutdown`.
- Components hold executors by composition. The session shuts each executor
  down right after its owner's `shutdown`, so a component writes no cleanup
  for it.
- `submit` returns `redsun.compute.Future`, a subclass of
  `concurrent.futures.Future` with `then(on_result, on_error=None)`. The
  callbacks run on the thread the frontend names for results, the main thread
  in a Qt session, or on the thread a `@slot(thread=...)` marker names, and
  are dropped once their owner has shut down.
- Pools are registry resources: generators in the session's registry, made on
  first request and stopped when the registry closes, last made first.
- Pools are internal to the session. A constructor or a `setup` asks for an
  executor and gets the same object for one owner and kind. A component
  asking for a pool is skipped with a message naming the executor, and a
  `provides` method returning a pool or an executor stops the build with
  `RegistrationError`.
- Pools are made while components are built, and started in the setup step
  after every component's `setup`. Only pools a built component holds are
  started.
- A call submitted before the start waits in the pool and runs first, in
  order, at the start. Before the start, `result()` and `exception()` with no
  timeout raise `RuntimeError`, and with a timeout they wait as usual.
- A pool that fails to start is broken: its waiting calls fail with
  `BrokenPool`, a subclass of `concurrent.futures.BrokenExecutor`, and
  `submit` raises it. The components holding the pool stay built.
- Pools count calls per owner under the names the Java metrics library
  Micrometer uses for its executors (`queued`, `active`, `completed`,
  `failed`, `pool_size`, `longest_idle`). An executor reports its owner's
  counts, and the session logs each pool's totals at shutdown.
- The thread pool is shared by every component. Each component asking for a
  `ProcessExecutor` gets a `ProcessPool` of its own, under a registry key
  holding its name, sized from its share of the compute cores unless the
  session file gives a count.
- `ProcessPool` holds a `concurrent.futures.ProcessPoolExecutor` started with
  `spawn`. Each worker sets the pool's priority, limits its native libraries
  to one thread and sends its log records to the session through a queue as
  it starts.
- When a worker dies, every unfinished call of its pool fails with
  `WorkerCrashed` once the pool has replaced the standard executor. Nothing
  is sent again on its own. A pool whose workers die more than 3 times within
  60 s is broken.
- `submit` on a `ProcessExecutor` refuses a function a worker cannot import
  by name before anything starts.
- No new build step: the work fits the registry, presenters, views and setup
  steps.

## Consequences

- A component gets threads by adding one parameter, and a test passes it the
  `inline_threads` fixture, which runs each call in the test's thread.
- The session decides the pool's size and the native thread limits, so the
  `compute` section of a session file changes them for every component at
  once, and no component can start more threads than the session allows.
- `submit` refuses work once the session has shut down, so a view cannot
  start work from Qt's `closeEvent`.
- Nothing existing changes. A session whose components ask for no executor
  makes no pool and changes no limit.
- A crash in one component's worker fails only that component's calls, but
  it fails all of them, including calls the crash had nothing to do with. A
  component decides in its error callback whether a call is safe to send
  again.
- A script that builds a session with worker processes starts it under
  `if __name__ == "__main__":`, since `spawn` imports the script in every
  worker.
- A later release adds pools of NVIDIA GPU streams as a further `Pool` and
  executor pair, reusing the same start, counts and shutdown.
