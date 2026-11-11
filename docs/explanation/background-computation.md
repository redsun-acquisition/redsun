---
icon: lucide/cpu
---

# How background computation works

A component often has work that takes longer than a frame of the window, such
as the median of a scan's frames or a fit to a stack of images. Run where the
component received its data, that work holds up whatever else that thread
does: on the main thread, the window freezes. So `redsun` lets the component
hand that work to threads the session owns, sizes, starts and stops.
[How to run background processing](../how-to/run-background-processing.md)
shows the steps; this page explains why the session holds the threads and
what it does with them.

## Why the session owns the threads

A component knows what it wants to compute and when, usually from the
[documents](glossary.md#document) of a run. It doesn't know how many cores the
computer has, which other components compute at the same time, or what the
libraries it calls already started. The session knows all of that, so it
makes the decisions that need it: how many threads to start, how many
threads each library may start on its own, when the threads start and what
happens to a call whose component has gone.

Qt's `QThreadPool.globalInstance()` works the same way: the code that runs a
task asks for the shared pool and never builds one. A component that built
its own pool would size it as if it were alone on the computer, and two such
components would each start a thread per core.

## Pools and executors

The session keeps two kinds of object apart. A [pool](glossary.md#pool) owns
the threads, and every component of a session shares it. An
[executor](glossary.md#executor) is one component's handle on the pool: it
sends that component's calls to the pool and keeps track of them. The
component that holds an executor is its [owner](glossary.md#owner), and the
executor carries the owner's name into every count and log line.

A component asks for an executor by annotating a constructor parameter with
[`ThreadExecutor`][redsun.compute.ThreadExecutor]. It never sees the
pool, so it cannot stop the threads that other components use, and it doesn't
write a `shutdown` for the executor either: the session shuts the executor
down right after the component's own `shutdown`.

Splitting the two lets each `shutdown` mean one thing. An executor's
`shutdown` keeps the contract of `concurrent.futures.Executor`, scoped to its
owner's calls: `submit` raises afterwards, calls still waiting can be
cancelled, and calls already running finish. The pool goes on serving the
other owners. A pool's `shutdown` stops the threads themselves, which only the
session, or a script that built the pool, does.

[ADR 38](decisions/0038-the-session-owns-background-computation.md) records
the alternatives weighed for this split.

## When the pools start

The session makes a pool when the first component that asks for it is built,
and starts it after every component's [`setup`](glossary.md#setup) has
returned. Only a pool that a built component holds is started, so a pool
whose components all failed to build never starts a thread.

The later start lets a `setup` prepare work before any run. A call submitted
from `setup` waits in the pool, and the pool runs the waiting calls first, in
the order they came, when it starts. `setup` cannot wait for such a call,
though, since the pool starts only after `setup` returns. That is why
[`Future.result`][redsun.compute.Future.result] without a timeout refuses
with a `RuntimeError` while its call waits for the pool to start, instead of
waiting forever.

A pool whose threads cannot be made is broken: its waiting calls fail with
[`BrokenPool`][redsun.compute.BrokenPool], and `submit` raises it for every
later call. The
components holding it stay built, because by then every component has been
built and set up. The build summary lists the broken pool.

When the session shuts down, the pools stop after every component and its
executors, and before the devices disconnect and the services stop.

## Results on the component's thread

`submit` returns a [`Future`][redsun.compute.Future], the standard
`concurrent.futures.Future` with one more method, `then`. `then` takes a
callback for the result and one for the exception, and runs them on the
thread the frontend names for results: in a Qt session the main thread, where
a widget may be touched. A callback marked with `@slot(thread=...)` runs on
the thread the marker names instead. Qt's `QFuture::then` works the same way,
running its continuation on the thread of a context object.

A callback belongs to the executor's owner, so once the session has shut the
owner down, a result that arrives later is dropped instead of calling into a
component that no longer runs. `QFuture::then` drops a continuation whose
context object was destroyed for the same reason.

## Compute cores and presets

The session sizes its pool from the [compute cores](glossary.md#compute-cores):
the physical cores of the computer, less one kept for the window's thread. A
physical core counts once even when it runs two hardware threads, because
the two threads of one core share its arithmetic units, and two numerical
threads on one core run no faster than one.

A preset splits the compute cores `C` between the pool's threads and the
threads each call's native libraries may start:

| preset | pool threads | native threads per call |
| --- | --- | --- |
| `latency` | 1 | `C` |
| `balanced` (default) | `max(2, C // 4)` | `C // pool threads` |
| `throughput` | `C` | 1 |

`latency` suits one large computation at a time, which a library such as
`numpy` spreads over every core itself. `throughput` suits many small calls,
each on one core. The `compute` section of the session file picks the preset
and changes the count;
[Compute](../reference/session-file.md#compute) lists its keys.

## Native thread pools

Many numerical libraries start threads of their own. `numpy` runs matrix
products on a BLAS library such as OpenBLAS, and other libraries run loops on
OpenMP, and each sizes its threads to the whole computer when it loads. A
pool of eight threads, each calling a library that starts sixteen threads,
asks for 128 threads on sixteen cores, and the threads spend their time
waiting for each other.
[Who controls parallelism?](https://pythonspeed.com/articles/parallelism-slower/)
explains how the threads `numpy` starts for BLAS compete with a program's own
parallel work, and limits them with `threadpoolctl`.

So the session limits them, with `threadpoolctl` for BLAS and OpenMP and
`torch.set_num_threads` when PyTorch is loaded. It sets the limit from the
main thread when the pools start, and each pool thread sets it again for
itself as it starts, because OpenMP keeps a limit per thread. A limit reaches
only the libraries already imported at that moment; a library imported later
starts at its own size.

The limits apply only when a built component holds a pool, so a session that
computes nothing in the background leaves every library as it found it. The
session puts the old limits back when it shuts down.

## The GIL

A thread helps only when the work lets go of the GIL, the lock that lets one
thread at a time run Python code. `numpy`, BLAS and most compiled code let go
of it while they compute, so the window's thread and the pool's threads run
at the same time. A function written in plain Python holds the GIL while it
runs, so it takes turns with the window's thread instead and slows it down.

The session watches for that. A thread of its own wakes every 50 ms, and when
it wakes more than 0.2 s late, the session logs the functions the pool was
running at that moment. The `switch_interval_ms` key of the session file
changes how often Python passes the GIL between threads, and is left alone
unless you set it.

A later release adds pools of worker processes for code that holds the GIL,
and pools for NVIDIA GPUs.
