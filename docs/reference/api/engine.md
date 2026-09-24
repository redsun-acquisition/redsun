---
icon: lucide/code
---

# Engine

## Run engine

::: redsun.engine
    options:
      members:
        - RunEngine
        - Deferrals
        - Status
        - RunEngineResult

## Actions

::: redsun.engine.actions
    options:
      members:
        - continous
        - Action
        - SRLatch
        - ContinousPlan

## Plan stubs

::: redsun.engine.plan_stubs
    options:
      members:
        - wait_for_actions
        - describe
        - describe_collect
        - lock
        - unlock
        - lock_wrapper
