# 2. Storage dual-context redesign

Date: 2026-07-24

## Status

Accepted

## Context

`BaseStorage` is async-only: `__call__` is a coroutine returning a primed
async generator (`FrameSender`), so frames can only be pushed from the device
layer. Two producer contexts need the same store:

- **Device layer (async):** ophyd-async `StandardDetector` logic
  decomposition (`TriggerLogic` / `AcquireLogic` / `DataLogic`) pushing
  frames during the prepare → kickoff → complete → collect cycle.
- **Callback layer (sync):** `DocumentRouter` presenters running inside the
  RunEngine's `emit_sync` on the loop thread — they can never await.

The async-only sink API forces callback-side work to be modelled as a fake
device: `MedianDevice` in redsun-mimir is a `StandardDetector` whose polling
`_pump` exists only to reuse the writer. A `write_sig` soft signal further
patches the gap between "kickoff = start live view" and "now also write".

The `StorageStateMachine` (UNSEALED → SEALING → OPEN → CLOSING, `try_seal`
first-writer race, `await_open` parking) exists solely because store-open is
inferred from the first arriving frame — nothing tells the storage a write
window started. The `StandardDetector` cycle provides explicit lifecycle
moments the current design ignores.

A redsun-specific constraint shapes everything: **live view without
storage** — a staged, kicked-off detector streams frames to viewers
indefinitely, and today's live plans (`live_stream`, `live_median_scan`)
re-run stage/prepare/kickoff every loop iteration while writing only happens
if a stream action fires. Any design that opens a store eagerly at prepare
would create empty stores on every idle iteration.

Guiding principles agreed for the redesign:

- Plans stay generic: only stock bluesky verbs; documents are the interface;
  callbacks decide what to consume. No storage-aware plan stubs.
- Stick close to the ophyd-async `data_logic` design for data producers.
- Backwards compatibility is explicitly not required.

## Decision

### Transport: bounded `culsans.Queue` per `data_key`

Replace the `FrameSender` generator machinery (`_pusher`, `asend`, priming)
with one bounded [culsans](https://github.com/redsun-acquisition/culsans)
queue per registered key (`maxsize` default 100, overridable per
`BaseStorage`). Device producers keep generator-era backpressure via
`await put`; the bound caps RAM if the backend falls behind. culsans is
thread-safe and same-thread-safe: `green_put(blocking=False)` never blocks,
so it is safe inside `emit_sync` on the loop thread.

### `FrameSink`: producer-face-only handle

`BaseStorage.sink(data_key)` returns a thin wrapper exposing only:

- `await sink.put(frame)` — device layer; parks on a full queue.
- `sink.put_nowait(frame)` — callback layer; raises `QueueFull` /
  `QueueShutDown` loudly.
- `sink.close()` — sync, idempotent; shuts the queue down cleanly (queued
  frames still written). Devices call it from `DataLogic.stop`/unstage,
  presenters on the stop document. No-op if capacity already shut the queue.

The consumer face (`async_get`, `clear`, immediate shutdown) stays private to
the drain. Producers cannot consume frames. Frames may be enqueued before the
store opens; they wait in the queue.

### Drain: one `BaseStorage`-owned task per key, spawned by `sink()`

`sink(data_key)` creates the queue and spawns the drain task — legal from
sync code because every caller (async device prepare, `emit_sync` callback)
runs on the loop thread. The drain loop is the old `_pusher` inverted:
`await queue.async_get()` → ensure open → `await store.write(key, frame)` →
`router.mark_written(key)` → count. `FrameRouter.mark_written` remains the
single counter-advance point; ophyd-async `complete()` machinery is untouched
(it waits on `collections_written_signal` = `signal_for(key)`).

All per-key teardown flows through the drain's exit path: whether the queue
was shut by capacity, `sink.close()`, or `storage.close()`, the exiting drain
retires its router entry, and the last drain out closes the backend under the
open lock. No separate release API, no double-release ambiguity.

### Open: idempotent, lock-guarded, two entry points

`await storage.open()` behind an `asyncio.Lock`: the first caller opens the
backend; concurrent and later callers await/return on the same open. Entry
points:

- **Eager (optional):** `DataLogic.prepare` calls it — stock ophyd-async
  writer behaviour ("prepare means writing is imminent"). Snap-style
  acquisition detectors opt in.
- **Lazy (always on):** the drain calls it before its first write. Live-view
  devices and callback-only bursts rely on this — the store materialises on
  the first frame actually written, never earlier.

Path allocation stays at first `register` (cheap, no backend I/O), so
`DataLogic.prepare_unbounded` can build its `StreamResourceDataProvider`
(`uri_for` / `resource_info_for` / `signal_for`) before any store exists.

### Close: last drain out closes; flush on clean stop, drop on abort

- Clean (`sink.close()` / `storage.close(flush=True)`): `queue.shutdown()` →
  drain finishes queued frames, then exits.
- Abort (`reset_group` / `storage.close(flush=False)`):
  `queue.shutdown(immediate=True)` → queued frames dropped, fast close.

A burst where no frame ever flowed (live iteration whose action never fired)
is trivial cleanup: the drain exits without ever having opened, clearing its
router entry and the path. Symmetric register/teardown per plan-loop
iteration — no leaked router entries.

### Capacity: enforced by the drain, signalled by the queue

The drain counts writes; at `spec.capacity` it calls `queue.shutdown()` and
exits. An overrunning producer's next `put` raises `QueueShutDown` — the
queue-era analogue of the generator returning. Unbounded specs drain until
close. Capacity remains control flow; nothing raises `StopAsyncIteration` by
hand.

### Registration: sync, before open only

`register(spec)` is plain sync (the async `register` / planned
`register_nowait` split dissolves) and raises `StoreStateError` while open.
Applies to callbacks too: a callback that wants a new key derives its
`StreamSpec` from a **descriptor document** (which carries shape/dtype for
the devices in the plan) and registers before any drain has opened the store
for that burst. Late-joining an already-open store is unsupported.

### `StorageStateMachine` deleted

With explicit `open()` arbitrated by a lock and close by last-drain-out
refcounting, the four-state machine, `try_seal`, `await_open`, `open_failed`,
`ensure_registrable`, and the first-writer race choreography have nothing
left to arbitrate. Misuse (register while open, put after capacity, double
open) raises a single `StoreStateError`, replacing `InvalidStoreState`.

### Process-wide registry keyed by `(group, mimetype)`

`register_storage(...)` raises on duplicate, `get_storage(...)` raises loudly
on missing, `reset_group(...)` is async teardown (close with drop). Devices
and presenters resolve the same `BaseStorage` instance without constructor
threading.

### Live view stays out of storage

The acquisition loop always updates the device's buffer signal for viewers;
it pushes into a `FrameSink` only while a write window is active. Storage
never sees a frame it will not write.

### API surface

```python
class BaseStorage:                                 # implements SinkFactory
    def register(self, spec: StreamSpec) -> None   # sync; StoreStateError if open
    def sink(self, data_key: str) -> FrameSink     # sync; one live sink per key
    async def open(self) -> None                   # idempotent ensure-open
    async def close(self, *, flush: bool = True) -> None
    def uri_for(self, data_key: str) -> str
    def resource_info_for(self, spec: StreamSpec) -> StreamResourceInfo
    def signal_for(self, data_key: str) -> SignalR[int]

class FrameSink:
    async def put(self, frame: NDArray) -> None    # device layer, backpressure
    def put_nowait(self, frame: NDArray) -> None   # callback layer, loud failure
    def close(self) -> None                        # sync, idempotent, flush semantics
```

### Lifecycle walkthroughs

**Bounded acquisition (snap):** `TriggerLogic.prepare_internal` →
`register(spec)`; `DataLogic.prepare_unbounded` → eager `await open()` +
build provider; kickoff → producer `await put(frame)`; drain writes, counters
advance; capacity → queue shutdown, drain exits; `complete` observes the
counter; unstage → last drain out closes with flush.

**Live plan (today's shape, transitional):** stage/prepare/kickoff each
iteration registers keys and allocates a path, opens nothing. Live frames go
to the buffer signal only. Stream action flips `write_sig` → producer starts
`put`ting → first written frame lazily opens the store → capacity →
complete/collect/unstage → drains exit → close. Iterations without an
action create no store.

**Median flow:** descriptor doc → presenter derives `StreamSpec`, registers,
obtains its sink (drain parked on an empty queue); Event docs (from
`trigger_and_read` / `create`+`save` in the scan) carry the frames; presenter
accumulates per run-uid, computes the median → `put_nowait` → drain lazily
opens and writes → stop doc → `sink.close()` → drain flushes and exits.

## Consequences

- **Deleted:** `FrameSender`, `BaseStorage._pusher`, generator priming and
  the `_sinks` generator map; `StorageStateMachine`, `StorageState`,
  `InvalidStoreState` and their tests; async `register`.
- **Preserved:** the `StorageIO` (mechanics) / `OpenStore` (lifecycle handle)
  split; `FrameRouter.mark_written` as the single counter-advance point;
  capacity as control flow.
- **Error handling:** backend open failure propagates from the opening drain
  and the lock releases (retryable); `QueueFull` on `put_nowait` is loud,
  never silently dropped.
- **Testing:** `tests/sdk/storage/test_fsm.py` is replaced by lifecycle tests
  against the public interface: one happy-path test driving register → sink →
  put → open → capacity → close asserting backend contents via `MemoryIO`,
  plus focused unhappy paths (register-while-open, put-after-capacity,
  abort-drop vs clean-flush, burst-died-without-frames) and a concurrency
  test (several keys putting concurrently — single backend open, all frames
  written). In addition, **integration tests execute real plans through the
  `RunEngine`** combining a disk-writing device (mock detector built on the
  ophyd-async logic decomposition, backed by `MemoryIO`) with a
  `DocumentRouter` callback that consumes the emitted documents and writes a
  derived key through the sync API — pinning the dual-producer behaviour
  `live_median_scan` will rely on after the mimir rework.
- **redsun-mimir (staged separately, enabled by this ADR):** `MedianDevice`
  and its logics/signals are deleted — median computation moves to
  `MedianPresenter` consuming Event documents. After the plan rework makes
  the sink lifecycle the write window (prepare → kickoff → capacity →
  complete as a plain bounded fly segment), `write_sig` is deleted too. Until
  then, today's plan shapes keep working unchanged against the new storage
  layer.
- **New dependency:** culsans (redsun-acquisition fork) becomes a hard
  runtime dependency of redsun.
