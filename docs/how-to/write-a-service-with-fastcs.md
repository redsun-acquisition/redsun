---
icon: lucide/server-cog
---

# How to write a service with FastCS

Write a [service](../explanation/glossary.md#service) with `fastcs`, serve it
over [PVAccess](../explanation/glossary.md#pvaccess), and point a device at
it. [How to write a service](write-a-service.md) does the same with `caproto`
over [Channel Access](../explanation/glossary.md#channel-access), and covers
what is common to every service.

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

!!! tip "`fastcs` and type checkers"

    `fastcs` ships no `py.typed` file, so a type checker cannot see its
    types and may complain about code that uses it. `mypy` says:

    ```text
    Skipping analyzing "fastcs.controllers": module is installed, but missing
    library stubs or py.typed marker  [import-untyped]
    ```

    and, in strict mode, about the class you write:

    ```text
    Class cannot subclass "Controller" (has type "Any")  [misc]
    ```

    The code is correct. To quiet both, add this to the configuration of
    `mypy` in your `pyproject.toml`:

    ```toml
    [[tool.mypy.overrides]]
    module = ["fastcs.*"]
    ignore_missing_imports = true

    [[tool.mypy.overrides]]
    module = ["stage_fastcs"]
    disable_error_code = ["misc"]
    ```

## Write the controller

`fastcs` describes a piece of hardware as a controller with attributes. In a
file called `stage_fastcs.py`:

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

The service is ready once it answers. `until_served` checks that by asking
for the record in which `fastcs` lists the attributes of the controller:

```{.python}
--8<-- "docs/examples/stage_fastcs.py:ready"
```

## Write the device

In the file of the session, in the same folder:

```{.python}
--8<-- "docs/examples/device_fastcs.py:device"
```

The device names no
[process variable](../explanation/glossary.md#process-variable).
[`fastcs_connector`][ophyd_async.fastcs.core.fastcs_connector] reads the
record that lists the attributes, and fills in every signal the device
declares. The device says it has a `position`, and the connector finds it.

## Declare the service

```{.python}
--8<-- "docs/examples/device_fastcs.py:session"
```

[`Launch`][redsun.Launch] names the module and the line it prints when it is
ready. `config` names the
[transport](../explanation/glossary.md#transport): every service of a session
speaks the same protocol, which is Channel Access unless the session says
otherwise.

`StagePresenter` and `StageView` are the ones of
[Describing a device with a protocol](../tutorials/device-protocols.md). The
whole scripts are at the end of the page.

## Run it

Run the session from the folder that holds both files, since that is where it
looks for `stage_fastcs`:

```bash
python device_fastcs.py
```

```text
Service 'stage_service' started
Services started: 1/1
Container built: 1/1 devices, 1/1 presenters, 1/1 views
```

Press the button of the stage: it moves a stage that `fastcs` serves.

??? example "The whole scripts"

    The service, `stage_fastcs.py`:

    ```{.python}
    --8<-- "docs/examples/stage_fastcs.py"
    ```

    The session, `device_fastcs.py`:

    ```{.python}
    --8<-- "docs/examples/device_fastcs.py"
    ```
