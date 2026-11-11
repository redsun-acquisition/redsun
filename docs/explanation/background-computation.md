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

A pool whose threads or worker processes cannot be started is broken: its waiting calls fail with
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
main thread when the thread pool starts, and each of its threads sets it again for
itself as it starts, because OpenMP keeps a limit per thread. A limit reaches
only the libraries already imported at that moment; a library imported later
starts at its own size.

The limits apply only when a built component holds a thread pool, so a
session that computes nothing in the background, or only in worker processes,
leaves every library of its own process as it found it. The
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

## Worker processes

Code that holds the GIL runs alongside the window only in another process, so
a [`ProcessExecutor`][redsun.compute.ProcessExecutor] sends its calls to the
session's [worker processes](glossary.md#worker-process). Each worker runs
`python -m redsun.workers`, which the session starts the way it starts a
[service](glossary.md#service): without a console window, each line it prints
logged under its name, ready once it prints a line saying so, and stopped by
closing its standard input. Each worker gets one native thread, through
`OMP_NUM_THREADS` and the matching variables of OpenBLAS and MKL in its
environment, because there are as many workers as `processes` asks for and
each would otherwise start a thread per core. The `compute` section's
`processes` key sets the count, one by default.

Only values cross between the processes, never live objects, because each
call and its result are pickled. A function travels by its module and its
name, and the worker imports the module on the first call. That is why
`submit` refuses a lambda, a function defined inside another one and a bound
method: none of them has a name a worker can import, and a bound method
would also carry its component along. A module that imports `qtpy` loads Qt
in every worker that imports it, which costs memory and start time for
nothing, so the worker logs a warning naming the function when that happens.

A pipe from `multiprocessing.connection` carries each call and its answer.
Arrays larger than 64 KiB travel beside the pipe, through two shared-memory
rings per worker made with `sharedbox` when it is installed, so the pipe
carries only their description. A ring is made with the first large array and
grows when a larger one comes. Each ring holds four arrays of the largest
size sent so far, so four workers exchanging 32 MiB arrays reserve about
1 GiB of shared memory, far more than the 64 MiB a container gets for
`/dev/shm` by default. Without `sharedbox`, every array travels through the
pipe, which is slower for large ones, and an info line in the log names the
`sharedbox` extra. For one large send at the end of a run, a block of shared
memory the component fills as the data arrives beats both, as
[How to run background processing](../how-to/run-background-processing.md#send-large-arrays-through-a-shared-block)
shows.

On an interpreter running without the GIL, a `ProcessExecutor` runs its calls
on threads of the session's own process, since threads no longer take turns
there. It still pickles each call and its result, so code that works there
also works with worker processes.

## Crashes

A worker can die in the middle of a call, from a crash in compiled code or an
`os._exit`. The session logs the worker's exit code and its last output,
starts a new worker in its place and sends the call again, so a single crash
doesn't fail the call. Sending a call again repeats what it did before it
crashed, such as writing a file. A call that has ended 3 workers fails with
[`WorkerCrashed`][redsun.compute.WorkerCrashed] instead, so a call that
always crashes fails on its own while every other owner's calls go on. A pool
that has to start more than 5 new workers within 60 s stops trying: it is
broken, and its calls fail with [`BrokenPool`][redsun.compute.BrokenPool].

Only a closed pipe counts as a crash. An error in the call itself, or one on
the session's side of the pipe such as running out of shared memory, fails
that call and leaves the pool's count of crashes alone.

## Priority

The worker processes start at the priority the `compute` section names:
`low`, `normal` or `high`, `normal` by default. The setting belongs to the
pool rather than to a component or a call, because one worker runs the calls
of several components, and on Linux and macOS a process can lower its own
priority but never raise it back. On Windows the session starts each worker
with the matching priority class; on Linux and macOS it sets the worker's
nice value to 10 for `low` or -10 for `high` right after starting it.

Raising a priority there needs root, or the `CAP_SYS_NICE` capability on
Linux. When that is refused, the session logs one warning for the pool and
starts its workers at normal priority instead of stopping the build. Priority
is the only say `redsun` takes over where work runs: no thread or process is
tied to particular cores.

A later release adds pools for NVIDIA GPUs.
