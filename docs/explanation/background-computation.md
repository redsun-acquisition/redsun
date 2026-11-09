---
icon: lucide/cpu
---

# Background computation

A session keeps one pool of threads for heavy computation and gives every
component that asks for one an [executor](glossary.md#executor): its own share
of that pool. The session sizes that pool from the machine's cores, limits the
threads of the libraries the work calls, and hands each result back on the
thread its component lives on. [How to run background processing](../how-to/run-background-processing.md)
shows the code a component needs.

## Why the session owns the threads

Only the session knows the whole machine and every component on it, so only
the session can size a pool that fits. A component that made its own pool
would size it to the machine, and so would the next one, until ten components
each start sixteen threads on a sixteen-core laptop. The libraries the
computation calls make it worse, because `numpy` hands matrix arithmetic to
BLAS, which starts a thread per core of its own the first time it runs. A
session that owns the pool can size it once, limit those libraries to match,
and stop everything when it shuts down.

The decision and the options set aside are recorded in [ADR
0038](decisions/0038-the-session-owns-background-computation.md).

## Threads and the GIL

A thread speeds up a computation only while the computation runs native code,
because Python's GIL lets one thread at a time run Python code in a process.
Most of `numpy` releases the GIL while it works, so a median computed in a
pool thread leaves the main thread free. Measured on a 16-core laptop, with
`np.median` over 40 frames of 2048 x 2048 `uint16`:

| Case | Time |
| --- | --- |
| The median alone | 2.39 s |
| Two medians in two threads | 2.58 s together |
| Two medians one after the other | 4.78 s |

While the median ran in a thread, a pure Python loop on the main thread kept
its full speed. A `napari` viewer showing frames at 30 Hz kept 30 frames per
second during the median, which took 2.84 s instead of 2.54 s with no viewer,
because the two shared the memory bandwidth.

Code that holds the GIL, such as a loop written in Python, gains nothing from
a thread. It takes turns with the main thread, so the window answers more
slowly while it runs. Such code needs a process of its own, which is later
work (see [What comes next](#what-comes-next)).

## The budget

The session counts the physical cores of the machine, keeps one of them for
the rest of the application, and spends what is left, the budget, on
computation. It counts physical cores rather than logical CPUs, because the
two hardware threads of one core share its arithmetic units: two BLAS threads
on the two CPUs of one core ran no faster than one thread. On Windows and
Linux the session reads the count from the operating system. Elsewhere it
uses `os.cpu_count()` and logs a warning.

A preset then splits the budget `B` between the threads of the pool and the
native threads each of them may use:

| Preset | Pool threads | Native threads per pool thread |
| --- | --- | --- |
| `latency` | 1 | `B` |
| `balanced` | `max(2, B // 4)` | `B // pool threads` |
| `throughput` | `B` | 1 |

On a 16-core machine the budget is 15 cores, so `balanced`, the default, gives
a pool of 3 threads that may use 5 native threads each. The build summary
shows the result in one line, `compute: balanced, 15 cores, 3 threads x 5
native`. The `compute` section of a [session file](../reference/session-file.md#compute)
picks the preset, caps the budget with `cores` and changes how many cores
`reserve` keeps.

## Native thread pools

The session limits the threads that native libraries start, because each of
them sizes itself to the whole machine: OpenBLAS started 24 threads on the
16-core laptop. The library `threadpoolctl` sets the limit for BLAS and OpenMP
together, and the session calls `torch.set_num_threads` as well when PyTorch
is loaded. Two facts decide when the limit is set:

- The limit holds for the whole process. While one thread held a limit of one
  thread, another thread's matrix product also ran on one thread, and took
  0.76 s instead of 0.13 s. So the session sets the limit once, and a computation
  never sets one around itself.
- The limit reaches only libraries already loaded. A limit set before
  `import numpy` left OpenBLAS at 24 threads. So the session sets it after
  every component's `setup` has run, and again as each pool thread starts, for
  a library imported since.

The session sets the limits only when a component it built took an executor,
so a session that computes nothing in the background leaves every library as
it found it. It puts the original sizes back when it shuts down. A library
with a setting of its own, such as the `workers` argument of `scipy.fft`, is
out of the session's reach: read
[`native_threads`][redsun.compute.ThreadExecutor.native_threads] from the
executor and pass it on.

## The switch interval

`switch_interval_ms` sets how often Python lets another thread take the GIL,
through `sys.setswitchinterval`. A shorter interval gives the main thread more
turns while a computation holds the GIL in short stretches, at the cost of
more switching. The session leaves the interval alone unless the key is set,
applies it under the same condition as the native limits, and puts the old
value back when it shuts down.

## Results on the component's thread

A result arrives on a pool thread, while the component usually wants it on
the thread it lives on, the main thread for anything that touches a widget.
[`deliver`][redsun.compute.deliver] makes that move. It queues the call to the
callback with `psygnal`, the library `redsun` connects signals with, and the
Qt session takes calls queued for the main thread from that queue as its event
loop runs. A callback marked with `@slot(thread=...)` goes to the thread it
names, with `"current"` naming the thread the session was built on, as it does
for a wired slot; any other callback goes to the main thread. The Qt session
empties the main thread's queue only, so another thread named there has to
call `psygnal.emit_queued` itself.

When no Qt session is running, as in a test, nothing takes calls from the
queue, so `deliver` calls the callback at once on the thread that finished the
computation. A computation that raised is logged with the callback's name and
never reaches the callback. One that was cancelled is logged at debug level
only, because shutting down cancels every call still waiting.

## Shutdown

The session stops its pool before it stops its services, so no computation
still waiting can ask a service that has gone. Calls that have not started are
cancelled. A call already running is left to finish, and the session doesn't
wait for it, though the process exits only once that call has finished. When
a Qt session shuts down, a result finishing after it is dropped and logged at
debug level, because the widgets it was meant for have gone.

## Calls that wait

A call that waited more than one second for a free thread is logged as a
warning under the logger `redsun.compute.<component>`, with the name of the
function and how long it waited. A pool too small for the work causes that
wait. Choose `throughput`, or give the budget more cores, when it keeps
appearing. The pool's threads are named `redsun-compute`, followed by a
number, which is how they show up in a profiler.

## What comes next

Three additions are planned on top of this executor. A process executor
will run code that holds the GIL in worker processes. Pinning will tie a
component's work to cores chosen in the session file. A CUDA executor will run
work on an NVIDIA GPU, one stream per device. None of them is in `redsun` yet.
