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

    The symbols below are wired up by the application container at startup and
    torn down on shutdown. They are documented so that the runtime's behaviour
    is inspectable, not so that components call them: installing a second
    backend, or building a loop alongside the shared one, breaks signal
    dispatch for the whole process. Use [`run_coro`](#redsun.aio.run_coro) to
    reach the shared loop.

::: redsun.aio.get_shared_loop

::: redsun.aio.set_async_backend

::: redsun.aio.CulsansAsyncioBackend

::: redsun.aio.AwaitableEvent
