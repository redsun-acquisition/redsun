# Engine

## Run engine

::: redsun.engine
    options:
      members:
        - RunEngine
        - Status
        - RunEngineResult
        - RunEngineInterrupted

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
        - read_while_waiting
        - read_and_stash
        - stash
        - clear_cache
        - describe
        - describe_collect
