---
icon: lucide/code
---

# Private API

Names `redsun` uses internally. They are documented so that a session can be
inspected, not for a component to call.

## redsun.aio { #redsun-aio }

!!! warning "Not part of the public API"

    A session sets these up when it is built and removes them at shutdown. A
    second backend, or a loop beside the shared one, breaks signal dispatch
    for the whole process. Reach the shared loop with
    [`run_coro`][redsun.aio.run_coro].

::: redsun.aio.get_shared_loop

::: redsun.aio.set_async_backend

::: redsun.aio.CulsansAsyncioBackend

::: redsun.aio.AwaitableEvent

## redsun.view.qt { #redsun-view-qt }

!!! warning "Not part of the public API"

    [`create_plan_widget`][redsun.view.qt.utils.create_plan_widget] calls this
    once for each parameter of a plan. Build the widgets of a plan through it.

::: redsun.view.qt._widget_factory
    options:
      members:
        - create_param_widget
      filters: ["!^_"]
