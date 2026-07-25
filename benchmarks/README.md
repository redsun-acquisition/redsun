# Benchmarks

Performance benchmarks for redsun's storage layer. These are **not** part
of the test suite (`pytest` does not collect them) and are **not** shipped
in wheels — they ride along in the sdist for reproducibility.

## Prerequisites

```bash
uv sync --group dev   # pulls acquire-zarr and the full dev environment
```

## `bench_acquire_zarr.py`

Measures the acquire-zarr backend in the dual-load scenario that mirrors
the mimir live-view target: two `StandardDetector`s share one
`BaseStorage`, and per frame each producer

1. updates its buffer signal — the plan `bps.monitor`s the signal, so
   every update synchronously emits a monitor Event document that a
   processing callback consumes inline (the live-view path), and
2. `await sink.put(frame)` into the bounded queue feeding the per-key
   drain that writes to the zarr store (the disk path).

```bash
uv run python benchmarks/bench_acquire_zarr.py --frames 200 --shape 512 512
uv run python benchmarks/bench_acquire_zarr.py --proc heavy --fps 60
uv run python benchmarks/bench_acquire_zarr.py --maxsize 10 --shape 2048 2048
```

Knobs: `--frames`, `--shape H W`, `--dtype`, `--maxsize` (queue bound),
`--fps` (producer pacing; `0` = free-running), `--proc none|light|heavy`
(callback workload), `--base-dir`/`--keep` (inspect the output store).

### Reading the report

| Metric | Bottleneck it points at |
|---|---|
| `live emission` per-frame time grows with `--proc` | Callback processing runs *inside* the producer's signal update (`emit_sync` is synchronous): live-view processing directly slows acquisition. If this dominates, processing must move off the emit path (queue it, decimate it, or thin the monitor rate). |
| `sink.put wait` per-frame time is large / max spikes | Backpressure: the drain (i.e. the zarr write) cannot keep up and the bounded queue fills. Compare against `--maxsize` — a larger bound absorbs bursts but delays the stall, it does not remove it. |
| `final flush (close)` is large | Frames were still queued when the plan ended — the writer lags the producers by roughly `maxsize` frames per key. |
| `effective throughput` (MB/s) far below disk capability | Per-frame overhead (queue hop, event emission, GIL contention between the two producer tasks) dominates over raw I/O; try `--proc none` to isolate the storage-only ceiling. |
| Both `put wait` and `live emission` small but plan time large | Look at the pacing (`--fps`) or the loop itself — everything shares one event loop thread. |

All timings are cooperative-scheduling measurements on the engine's event
loop, not isolated micro-benchmarks: that is the point — the contention
between live view and storage is exactly what the numbers surface.
