---
icon: lucide/code
---

# redsun.compute

Design rationale:
[ADR 0038](../../explanation/decisions/0038-the-session-owns-background-computation.md).

## Executors

::: redsun.compute
    options:
      members:
        - ThreadExecutor
        - deliver

## The budget

::: redsun.compute
    options:
      members:
        - Budget
        - Preset
        - budget
        - split
        - physical_cores
