# 38. The session owns background computation

Date: 2026-11-09

## Status

Accepted

## Context

Components such as a presenter computing the median of a scan need threads
for work too heavy for the main thread. Until now each component made its own,
usually a `ThreadPoolExecutor` sized to the machine, and every library it
called started a pool of native threads sized to the machine as well. With a
few such components a session ran several times more threads than the machine
has cores, and nothing stopped them when the session shut down.

Measurements on a 16-core laptop (AMD Ryzen 9 8940HX, 32 logical CPUs,
Windows 11, `numpy` 2.5.4) settled what the threads are good for:

- `np.median` over 40 frames of 2048 x 2048 `uint16` took 2.39 s. Two
  medians in two threads took 2.58 s together against 4.78 s one after the
  other, and a pure Python loop on the main thread kept its full speed while
  one ran. `np.median` releases the GIL, so a thread is enough for it.
- With a `napari` viewer showing frames at 30 Hz, the viewer kept 30 frames
  per second while the median ran in a thread, and the median took 2.84 s
  against 2.54 s with no viewer. In a process it took 2.91 s.
- Sending the 40 frames to a process as a list cost 0.8 s more than computing
  in place.
- OpenBLAS started 24 threads. A limit set with `threadpoolctl` held for the
  whole process: while one thread held a limit of one thread, another thread's
  matrix product took 0.76 s instead of 0.13 s. A limit set before
  `import numpy` did not reach OpenBLAS at all.

So the threads have to be sized by something that sees every component, and
the native limits have to be set once, after the libraries load, by the same
owner. That owner is the session. What remained open was how a component asks
it for threads. A session answers a constructor parameter from its
annotation, and three kinds of annotation were weighed.

A protocol is what a component already writes to ask for another component:

```python
class ThreadExecutor(Protocol):
    def submit(self, fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> Future[R]: ...


class MedianPresenter:
    def __init__(self, name: str, pool: ThreadExecutor) -> None: ...
```

The session answers a protocol with the built component of that shape, so a
component that happened to have a `submit` method would be passed in. A process
executor would have the same members, and the session warns when two
protocols it is asked for are interchangeable. Giving each protocol a member
only to tell them apart did not help: run against three protocols that differed
only in a `kind: Literal[...]` property, the shape matching found nothing to
separate them.

A factory object would let the component ask while it runs:

```python
class MedianPresenter:
    def __init__(self, name: str, compute: Compute) -> None:
        self._pool = compute.threads(2)
```

The build would then not know which components compute until they did, so it
could not size the pool, set the limits only when needed, or report what each
component took.

A concrete class is looked up by its exact type, never by shape:

```python
class MedianPresenter:
    def __init__(self, name: str, pool: ThreadExecutor) -> None: ...
```

The build reads the need from the signature, before the component exists, and
nothing else in the session can answer it.

## Decision

- An executor is a concrete `@final` class that `redsun` owns. The first is
  `redsun.compute.ThreadExecutor`, with `submit`, which has the signature of
  `concurrent.futures.Executor.submit`, `run`, its awaitable twin, and
  `native_threads`.
- A presenter or view asks for one by annotating a constructor parameter with
  the class. The session builds each component an executor of its own over one
  pool it owns, and passes it with the component's other arguments. A `setup`
  method, a provider or a session file key asking for or filling an executor
  stops the build.
- The session sizes the pool from a budget: the physical cores less a reserve,
  capped by `cores`, split by a preset, `balanced` by default. The class
  attribute `compute` and the session file's `compute` section set it, the file
  winning key by key.
- After every `setup` has run, and only if a component took an executor, the
  session limits the native thread pools loaded so far and sets the switch
  interval, then sets the native limits again as each pool thread starts. It
  restores both when it shuts down.
- `redsun.deliver(future, callback)` brings a result to the thread of the
  callback, through the queue `slot` already uses.
- The constructor, `ThreadExecutor(2)`, makes a pool of its own for scripts.
  The session never calls it.

```python
class MedianPresenter(DocumentRouter):
    def __init__(self, name: str, pool: ThreadExecutor) -> None:
        super().__init__()
        self._pool = pool

    def stop(self, doc: RunStop) -> RunStop:
        deliver(self._pool.submit(median_of, self._frames), self._publish)
        return doc
```

A decorator marking methods to run in the background was set aside, because
the component then no longer decides when the work starts or where the
result goes. So was a constructor wrapping a standard pool,
`ThreadExecutor(ThreadPoolExecutor(2))`, which would let a component bring
threads the session does not count.

## Consequences

- A component computing in the background gets threads sized for the machine
  and stopped with the session, without managing a pool.
- Every executor class to come, for processes or an NVIDIA GPU, is a class of
  its own the session recognises by name. Adding one changes the session.
- A session that took no executor leaves the native libraries alone; one that
  did limits them for the whole process, main thread included.
- A component that builds its own pool still can, and the session neither
  counts nor stops it.
