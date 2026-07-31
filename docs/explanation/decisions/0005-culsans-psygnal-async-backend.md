# 5. Culsans-backed psygnal async backend

Date: 2026-07-26

## Status

Accepted

## Context

Redsun's UI runs on the Qt main thread while device logic runs on a single
background `asyncio` loop. A view emits a signal; a presenter reacts to it by
awaiting hardware. psygnal already supports this shape directly - connecting a
coroutine function to a signal builds a coroutine callback that hands the call
to whatever async backend is installed - so no bridging code of our own is
needed at the call sites.

The stock backends could not carry that traffic:

- `AsyncioBackend.put` is `asyncio.Queue.put_nowait`, which is not thread-safe.
  Called from the Qt thread while the background loop sits idle, the queue's
  internal `call_soon` never wakes the parked loop: a signal emitted from the
  GUI was measured as undelivered after five seconds. A thread-safe hand-off
  delivers the same emission in well under a millisecond.
- `asyncio.Queue` binds to the loop that first awaits it while empty. The
  backend outlives any single loop - it is created once and lives for the
  process - so a queue bound to one loop raises once another is running, which
  is exactly what pytest's per-test event loops produce.

psygnal's `set_async_backend()` accepts only the three literal names
`"asyncio"`, `"anyio"`, and `"trio"`, so there is no public API for selecting a
backend of our own. Its teardown helper, `clear_async_backend()`, dispatches on
`isinstance` against the three concrete backend classes to decide whether to
close the queue.

## Decision

`redsun.aio.CulsansAsyncioBackend` implements psygnal's backend contract on a
[culsans](https://pypi.org/project/culsans/) queue, which is thread-safe on the
producing side by construction and is not bound to any one event loop. A drain
coroutine runs on the shared loop and dispatches each queued callback as its
own task, so a slow slot does not serialize the ones behind it.

The class is wired into psygnal at two levels, and both are load-bearing:

- It **inherits** `psygnal._async._AsyncBackend`, which supplies the abstract
  contract and makes the instance assignable where psygnal expects a backend.
  Virtual registration alone is invisible to a type checker.
- It is **registered as a virtual subclass** of `AsyncioBackend`, because that
  `isinstance` check is what makes `clear_async_backend()` call `close()`.
  Without it the backend is dropped with its queue and drain task still live.

Installation goes through `redsun.aio.set_async_backend()`, which assigns
psygnal's module global directly - the only way to install a backend that
`set_async_backend()` cannot name. It is idempotent and refuses to displace a
backend it did not install. The backend reports its name as `"culsans"`, so
psygnal's own setter raises rather than silently replacing it.

`QtAppContainer` owns the lifecycle: `build()` installs the backend before the
dependency-injection phase, since coroutine slots resolve a backend at connect
time, and `shutdown()` hands teardown back to psygnal's `clear_async_backend()`.

Exceptions raised inside a dispatched slot are logged on the `redsun` logger
through a task done-callback. Nothing awaits these tasks, so an unhandled
exception would otherwise surface only as asyncio's "task exception was never
retrieved" at garbage-collection time, or not at all.

## Consequences

- Redsun depends on two private psygnal symbols: `_AsyncBackend` as a base
  class and `_ASYNC_BACKEND` as the assignment target, plus
  `WeakCallback.dereference()` reached through the inherited `call_back`. A
  psygnal release that renames any of them breaks dispatch. The test suite
  pins the observable behaviour - installation, teardown, and delivery - so
  the break surfaces as a test failure rather than as silently dropped
  signals.
- culsans and aiologic become runtime dependencies. Both are pre-1.0.
- Only `QtAppContainer` installs a backend. Under a bare `AppContainer`,
  connecting a coroutine to a signal raises `RuntimeError` from psygnal.
- A failing slot no longer propagates anywhere a caller can see: emitters
  never learn that a slot raised, and the log is the only record.
- `close()` is synchronous and returns before in-flight callbacks finish. It
  shuts the queue down and lets the drain's exit path cancel outstanding
  tasks; awaiting their completion would require an async teardown entry
  point, which no caller has asked for yet.
