---
icon: lucide/server
---

# Putting a device behind a service

In this tutorial you add a third stage, which lives in a program of its own.
The session starts that program, and stops it when you close the window. It
continues from [Arranging the window](window-layout.md).

So far the stages kept their position in memory. Real hardware is reached
through a [service](../explanation/glossary.md#service): a separate program
that owns the hardware and offers its values over the network. Nothing you
wrote before changes. The new stage gets a row in the view of the stages, and
an entry in the plan widgets of `walk` and `scan`.

!!! warning "Devices without a service"

    A device can also reach its hardware on its own, but a service is the
    preferred way for now. See [Services](../explanation/services.md).

## Before you start

!!! note "What you need"

    `caproto`, to write the service, and `ophyd-async[ca]`, for the device to
    talk to it. Neither comes with `redsun`:

    ```bash
    uv add caproto "ophyd-async[ca]"
    ```

Open `first_session.py`, and add these imports below the ones it has:

```python
from typing import Annotated

from ophyd_async.epics.core import EpicsDevice, PvSuffix

from redsun import AsService, Declare, Launch
```

## 1. Write the service

Make a second file in the project folder, beside the first, called
`stage_ioc.py`. Start it with these imports:

```{.python}
--8<-- "docs/tutorials/stage_ioc.py:imports"
```

Then the stage:

```{.python}
--8<-- "docs/tutorials/stage_ioc.py:stage"
```

This is the whole stage: one value, named `Position`. `caproto` serves it
over [Channel Access](../explanation/glossary.md#channel-access), one of the
two protocols of [EPICS](../explanation/glossary.md#epics). A program of this
kind is called an [IOC](../explanation/glossary.md#ioc), and a value it serves
a [process variable](../explanation/glossary.md#process-variable).

This stage keeps a number. The service of a real stage would talk to its
controller in the same place: `caproto` can call a function each time
`Position` is set.

A service that a session starts has to do two more things. It stops when the
session asks, and it listens on this machine only. Add both below the stage:

```{.python}
--8<-- "docs/tutorials/stage_ioc.py:main"
```

[`identity`][redsun.services.identity] returns the name and
[prefix](../explanation/glossary.md#prefix) the session gave the service, or
`None` when the service runs alone; the service then falls back on `STAGE:`.
[`stop_on_request`][redsun.services.stop_on_request] stops the service as
++ctrl+c++ would once the session asks, and does nothing when it runs alone.

Try it alone:

```bash
uv run stage_ioc.py
```

It prints `Server startup complete.` and waits. Stop it with ++ctrl+c++, and
do not leave it running: the session starts its own. The service listens on
this machine only, so to read it with `caget` from another terminal, set
`EPICS_CA_ADDR_LIST=127.0.0.1` there first.

On Windows the service may print a few lines that end with
`OSError: [WinError 995]` as it stops. It has stopped all the same.

## 2. Write the device

In `first_session.py`, add a device below `FastStage`. Its position is the
process variable of the service:

```{.python}
--8<-- "docs/tutorials/device_service.py:remote"
```

The device names only the end of the process variable, `Position`. The
beginning, the prefix, comes from the service it is declared with. Like the
other stages it is a `StandardMovable`, whose one process variable is both its
setpoint and its readback.

## 3. Declare the service

Add the highlighted lines to the session: the service, the stage, and the
link that sends its position to the view.

```{.python hl_lines="3-6 9 24"}
--8<-- "docs/tutorials/device_service.py:session"
```

[`AsService`][redsun.AsService] declares a service, under the name on the
left of its line. [`Launch`][redsun.Launch] says how to start it: the module
to run, which is the name of the file, then the line it prints when it is
ready, and its prefix. [`Declare`][redsun.Declare] ties the stage to the
service, by the name the session gave it.

The prefix is written once, here. The session hands it to the service and to
the device.

## 4. Run it

```bash
uv run first_session.py
```

The session starts the service, waits for it, and then builds the rest. It
says so in the terminal:

```text
Service 'stage_ioc' started
Services started: 1/1
Session built: 4/4 devices, 5/5 presenters, 3/3 views
```

The window is the one of the last tutorial, with one more stage: the view of
the stages has a row for `remote_stage`, and the plan widgets of `walk` and
`scan` list it. Press its button, or choose it in a list of stages and press
**Run**: its position counts up, in a program that is not the one drawing the
window.

![The window of the last tutorial, with a third row in the view of the stages,
for remote_stage](images/device-service.png)

!!! note "Two messages you can ignore"

    Channel Access may print one or both of these messages, which look like
    errors:

    ```text
    Failed to start executable - "caRepeater".
    ```

    ```text
    CA.Client.Exception...
        Warning: "Virtual circuit disconnect"
    ```

    The first says that a helper program of EPICS is missing. The helper
    shares the announcements of servers between the programs of one machine,
    and without it a program takes longer to notice that a server has
    started again. The second says that the connection to the service
    closed while the session still used it: the service went away. Closing
    the window does not print it, since the session closes its connections
    before it stops the service.

!!! warning "One message you should not ignore"

    ```text
    CA.Client.Exception...
        Warning: "Identical process variable names on multiple servers"
    ```

    Another program the machine can reach serves `STAGE:Position` too, and
    the stage may be talking to that one: another IOC on the network, or,
    when your own `EPICS_CA_ADDR_LIST` names `127.0.0.1`, a `stage_ioc.py`
    left running in another terminal. On a network shared with others,
    choose a prefix nobody else uses.

## 5. Stop it

Close the window. The session stops the service it started:

```text
Service 'stage_ioc' stopped with exit code 0
```

??? example "The whole script"

    The service, `stage_ioc.py`:

    ```{.python}
    --8<-- "docs/tutorials/stage_ioc.py"
    ```

    The session, `first_session.py`:

    ```{.python}
    --8<-- "docs/tutorials/device_service.py"
    ```

## What you built

A service that serves a stage, and a session that starts it, talks to it and
stops it. The application now has three stages, a camera, five presenters
and three views.

This is the last tutorial.

## Next steps

- [Reusing the built-in positioner](builtin-positioner.md) is the next
  tutorial: it replaces the nudge presenter and view with the positioner
  `redsun` ships.
- [How to write a service](../how-to/write-a-service.md) serves a stage with
  `fastcs` over another protocol, and covers services that already run
  elsewhere, and what to do when one exits.
- [How to run a session without hardware](../how-to/run-without-hardware.md)
  runs the same window with no service behind it.
- [Services](../explanation/services.md) explains why devices and services
  are kept apart.
