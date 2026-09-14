# Async runtime

Design rationale:
[ADR 0005](../../explanation/decisions/0005-culsans-psygnal-async-backend.md).

## Running coroutines

::: redsun.aio
    options:
      members:
        - run_coro

## Internal machinery

!!! warning "Not part of the public API"

    The container sets these up at startup and tears them down at shutdown.
    They are documented so the runtime can be inspected, not for components to
    call: a second backend, or a loop beside the shared one, breaks signal
    dispatch for the whole process. Reach the shared loop with
    [`run_coro`](#redsun.aio.run_coro).

::: redsun.aio.get_shared_loop

::: redsun.aio.set_async_backend

::: redsun.aio.CulsansAsyncioBackend

::: redsun.aio.AwaitableEvent
