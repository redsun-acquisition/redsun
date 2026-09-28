---
icon: lucide/code
---

# redsun.aio

Design rationale:
[ADR 0005](../../explanation/decisions/0005-culsans-psygnal-async-backend.md).

## Running coroutines

::: redsun.aio
    options:
      members:
        - run_coro

The names a session sets the runtime up with are in the
[private API](private.md).
