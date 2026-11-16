---
icon: lucide/code
---

# redsun.compute

The pool of threads the session shares between its components, the pools of
worker processes it gives each component asking for one, and the executors a
component submits its calls through. Usage is in
[How to run background processing](../../how-to/run-background-processing.md).

## Executors

::: redsun.compute.ThreadExecutor
    options:
      show_root_heading: true
      inherited_members: true

::: redsun.compute.ProcessExecutor
    options:
      show_root_heading: true
      inherited_members: true

## Results

::: redsun.compute.Future
    options:
      show_root_heading: true

::: redsun.compute.BrokenPool
    options:
      show_root_heading: true

::: redsun.compute.WorkerCrashed
    options:
      show_root_heading: true

## Pools

::: redsun.compute.ThreadPool
    options:
      show_root_heading: true
      inherited_members: true

::: redsun.compute.ThreadPoolSettings
    options:
      show_root_heading: true

::: redsun.compute.ProcessPool
    options:
      show_root_heading: true
      inherited_members: true

::: redsun.compute.ProcessPoolSettings
    options:
      show_root_heading: true

::: redsun.compute.Limits
    options:
      show_root_heading: true

## Counts

::: redsun.compute.OwnerUsage
    options:
      show_root_heading: true

## Configuration

::: redsun.compute.Preset
    options:
      show_root_heading: true

::: redsun.compute.Priority
    options:
      show_root_heading: true

::: redsun.compute.ComputeSettings
    options:
      show_root_heading: true
