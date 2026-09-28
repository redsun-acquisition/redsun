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

Open `first_session.py`, and add these imports to the ones it has:

```python
from typing import Annotated

from ophyd_async.epics.core import EpicsDevice, PvSuffix

from redsun import AsService, Declare, Launch
```

## 1. Write the service

Make a second file beside the first, called `stage_ioc.py`. Start it with
these imports:

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

A service that a session starts has to do two more things. It stops when the
session closes its input, and it listens on this machine only. Add both
below the stage:

```{.python}
--8<-- "docs/tutorials/stage_ioc.py:stop"
```

```{.python}
--8<-- "docs/tutorials/stage_ioc.py:main"
```

Try it alone:

```bash
uv run stage_ioc.py
```

It prints `Server startup complete.` and waits. Stop it with ++ctrl+c++.

## 2. Write the device

In `first_session.py`, add a device below `FastStage`. Its position is the
process variable of the service:

```{.python}
--8<-- "docs/tutorials/device_service.py:remote"
```

The device names only the end of the process variable, `Position`. The
beginning, the [prefix](../explanation/glossary.md#prefix), comes from the
service it is declared with.

## 3. Declare the service

Add the highlighted lines to the session: the service, the stage, and the
link that sends its position to the view.

```{.python hl_lines="2-5 8 23"}
--8<-- "docs/tutorials/device_service.py:session"
```

[`AsService`][redsun.AsService] declares a service, and
[`Launch`][redsun.Launch] says how to start it: the module to run, the line it
prints when it is ready, and its prefix. [`Declare`][redsun.Declare] ties the
stage to the service by its name.

## 4. Run it

```bash
uv run first_session.py
```

The session starts the service, waits for it, and then builds the rest. It
says so in the terminal:

```text
Service 'stage_ioc' started
Services started: 1/1
Container built: 4/4 devices, 5/5 presenters, 3/3 views
```

The window is the one of the last tutorial, with one more stage: the view of
the stages has a row for `remote_stage`, and the plan widget of `walk` lists
it. Press its button, or choose it in the list of stages and press **Run**:
its position counts up, in a program that is not the one drawing the window.

!!! note "Two messages you can ignore"

    On a machine with no EPICS installed, Channel Access prints two messages
    that look like errors:

    ```text
    Failed to start executable - "caRepeater".
    ```

    ```text
    CA.Client.Exception...
        Warning: "Virtual circuit disconnect"
    ```

    The first says that a helper program of EPICS is missing, which a single
    machine does not need. The second appears when the service stops, and
    says that the connection to it closed.

## 5. Stop it

Close the window. The session stops the service it started:

```text
Service 'stage_ioc' stopped with exit code 0
```

## 6. Run without the service

Tell the session to mock its devices, by changing the last line of the
script:

```{.python hl_lines="2"}
if __name__ == "__main__":
    FirstSession({"mock": True}).run()
```

```bash
uv run first_session.py
```

```text
Services not started: the session is mocked
Container built: 4/4 devices, 5/5 presenters, 3/3 views
```

The window opens with no service behind it. Every device is a stand-in that
remembers what it is set to, so the buttons and the plan widgets still work.
Change the line back when you want the service again.

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
and three views, and the same window runs with the service or without it.

This is the last tutorial.

## Next steps

- [How to write a service with
  FastCS](../how-to/write-a-service-with-fastcs.md) serves a stage with another
  library, over another protocol.
- [How to write a service](../how-to/write-a-service.md) covers services that
  already run elsewhere, and what to do when one exits.
- [Services](../explanation/services.md) explains why devices and services
  are kept apart.
