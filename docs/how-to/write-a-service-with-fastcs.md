---
icon: lucide/server-cog
---

# How to write a service with FastCS

Write a [service](../explanation/glossary.md#service) with `fastcs`, serve it
over [PVAccess](../explanation/glossary.md#pvaccess), and point a device at
it. This page covers what differs from a `caproto` service.
[How to write a service](write-a-service.md) covers what is common to every
service: what a session needs from one, how to attach to one that already
runs, and what to do when one exits.

!!! note "Written for `fastcs` 0.14"

    The API of `fastcs` is still changing, and this page follows it. If a
    name on this page no longer exists in the version you installed, check
    the documentation of `fastcs`.

## Prerequisites

`fastcs[epicspva]`, to write the service, and `ophyd-async[pva]`, for the
device to talk to it. Neither comes with `redsun`.

=== "uv"

    ```bash
    uv add "fastcs[epicspva]" "ophyd-async[pva]"
    ```

=== "pip"

    ```bash
    pip install "fastcs[epicspva]" "ophyd-async[pva]"
    ```

## Write the controller

`fastcs` describes a piece of hardware as a controller with attributes:

```{.python}
--8<-- "docs/examples/stage_fastcs.py:controller"
```

`AttrRW` is an attribute that can be read and written, and `Float` says what
it holds.

## Serve it

```{.python}
--8<-- "docs/examples/stage_fastcs.py:serve"
```

- `FastCS` serves the controller over the transports it is given, here
  PVAccess.
- The session tells the service its
  [prefix](../explanation/glossary.md#prefix) through the environment
  variable `REDSUN_SERVICE_PREFIX`, and the controller is served under it.
- The service prints a line when it is ready, and stops when its standard
  input closes, as every service a session launches must.
- `fastcs` takes a prefix of letters, digits, `-` and `_`. `STAGE:` is
  accepted, since the last colon is taken off. `LAB:STAGE:` is refused.
- Over PVAccess a prefix has to be the only one of its name on the machine:
  two sessions serving the same one find each other's records.

## Say when it is ready

`fastcs` prints no line of its own when it starts to serve, so the service
finds out by asking. It asks for the record in which `fastcs` lists the
attributes of the controller, until it gets an answer. If serving has failed
meanwhile, it raises what made it fail:

```{.python}
--8<-- "docs/examples/stage_fastcs.py:ready"
```

## Point a device at it

```{.python}
--8<-- "docs/examples/device_fastcs.py:device"
```

The device names no
[process variable](../explanation/glossary.md#process-variable).
[`fastcs_connector`][ophyd_async.fastcs.core.fastcs_connector] reads the
record that lists the attributes, and fills in every signal the device
declares.

For the attribute `position` under the prefix `STAGE:`, `fastcs` serves three
records:

| Record | Holds |
| --- | --- |
| `STAGE:PVI` | the list of the attributes |
| `STAGE:Position` | the value to write |
| `STAGE:Position_RBV` | the value to read |

## Declare it, and name the transport

```{.python}
--8<-- "docs/examples/device_fastcs.py:declare"
```

[`Launch`][redsun.Launch] names the module and the line it prints when it is
ready. `config` names the
[transport](../explanation/glossary.md#transport): every service of a session
speaks the same protocol, which is Channel Access unless the session says
otherwise.

## Check that it starts

Run the session from the folder that holds the module of the service, since
that is where it looks for it. The session logs:

```text
Service 'stage_service' started
Services started: 1/1
```

## Quiet the type checker

`fastcs` ships no `py.typed` file, so a type checker cannot see its types.
`mypy` reports the import, and that of `p4p`:

```text
Skipping analyzing "fastcs.controllers": module is installed, but missing
library stubs or py.typed marker  [import-untyped]
```

and, in strict mode, the class written on top of it:

```text
Class cannot subclass "Controller" (has type "Any")  [misc]
```

To quiet both, add this to the configuration of `mypy` in `pyproject.toml`,
with the name of your module in the second entry:

```toml
[[tool.mypy.overrides]]
module = ["fastcs.*", "p4p.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["stage_fastcs"]
disable_error_code = ["misc"]
```

## The example in full

??? example "The service"

    ```{.python}
    --8<-- "docs/examples/stage_fastcs.py"
    ```

??? example "The session"

    The presenter and the view are the ones of the tutorial
    [Describing a device with a protocol](../tutorials/device-protocols.md).

    ```{.python}
    --8<-- "docs/examples/device_fastcs.py"
    ```
