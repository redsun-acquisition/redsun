---
icon: lucide/shapes
---

# Describing a device with a protocol

In this tutorial you add a second stage to the session, of a different class,
and the presenter and view you already wrote control it too. To get there,
you change how the presenter asks for its devices, and nothing in the view.
It continues from [Writing your first session](first-session.md).

You start by checking the types of the script. Then you write a
[protocol](../explanation/glossary.md#protocol), which describes the attributes
and methods a device must have, ask the session for the devices that satisfy
it, and add the stage.

## Before you start

!!! note "What you need"

    A type checker. This tutorial uses
    [`mypy`](https://mypy.readthedocs.io/), which doesn't come with
    `redsun`, so add it to the project as a development tool:

    ```bash
    uv add --dev mypy
    ```

Open `first_session.py` as you left it at the end of
[Writing your first session](first-session.md). You keep working in this
file until the last tutorial. Each tutorial adds to what's there, and when a
line you wrote has to change, the page shows it highlighted.

## 1. Check the types

```bash
uv run mypy first_session.py
```

Even though the script runs, `mypy` finds two errors in it:

```text
first_session.py:29: error: "Device" has no attribute "position"  [attr-defined]
first_session.py:30: error: "Device" has no attribute "position"  [attr-defined]
Found 2 errors in 1 file (checked 1 source file)
```

The line numbers in your file may differ, but the two lines are the ones in
`nudge` that read and set the position.

`devices` is a [`DeviceMapping`][redsun.DeviceMapping], which holds every
device of the session, of any kind. So all the type checker knows about one
of them is that it's a device, and not every device has a position.

## 2. Say what the presenter needs

The presenter needs only one thing from a stage, a `position` it can read and
set. Write that down as a protocol, above `StagePresenter`:

```{.python}
--8<-- "docs/tutorials/device_protocols.py:protocol"
```

Add the imports it needs below the ones the file has. The line
`from __future__ import annotations` stays first in the file:

```python
from typing import Protocol, runtime_checkable

from ophyd_async.core import SignalRW
```

`MyStage` doesn't inherit from `HasPosition`, and you don't change it. It
satisfies the protocol because it has a `position` of that type, which is
called [structural subtyping](../explanation/glossary.md#structural-subtyping).
[`runtime_checkable`][typing.runtime_checkable] lets Python make the same
check while the program runs, which the next tutorial relies on.

## 3. Ask for the devices that fit

Change the constructor of `StagePresenter` as highlighted. Where it asked for
a `DeviceMapping` under the name `devices`, it now asks for
[`DevicesOf[HasPosition]`][redsun.DevicesOf] under the name `stages`. The
rest of the class stays as it is:

```{.python hl_lines="2-4 6"}
--8<-- "docs/tutorials/device_protocols.py:constructor"
```

Add one more import, below the others:

```python
from redsun import DevicesOf
```

The session now passes only the devices that satisfy `HasPosition`, by name,
and leaves the others out. It reads what to pass from the type of the
parameter, so the name of the parameter is yours to choose.

!!! tip "Imports on more than one line"

    The file now imports from `redsun` on two lines, which Python allows.
    The whole script at the end of each page gathers such lines into one, as
    a formatter would. It also drops the import of `DeviceMapping`, which
    nothing uses for now. Leave it in your file, because a later tutorial
    needs it again.

## 4. Check the types again

```bash
uv run mypy first_session.py
```

```text
Success: no issues found in 1 source file
```

Run the script. The window hasn't changed, and the button moves the stage as
before:

```bash
uv run first_session.py
```

## 5. Add a second stage

Add a second device below `MyStage`. It starts at `5.0`, and it has a speed,
which the first one lacks:

```{.python}
--8<-- "docs/tutorials/device_protocols.py:device"
```

`FastStage` shares no code with `MyStage` and never mentions `HasPosition`,
but it satisfies the protocol all the same.

## 6. Add it to the session

Add the highlighted lines to the session. They declare the stage, and add the
link that sends its position to the view:

```{.python hl_lines="4 11"}
--8<-- "docs/tutorials/device_protocols.py:session"
```

Check the types, then run the script:

```bash
uv run mypy first_session.py
uv run first_session.py
```

```text
Session built: 2/2 devices, 1/1 presenters, 1/1 views
```

![The window of the session, with a row for each stage: a Nudge button and a
position](images/device-protocols.png)

The view has a second row, for `fast_stage`, which starts at `5.0`. Press its
button: `fast_stage` moves to `5.5`, and `stage` stays where it is.

One presenter and one view now control two stages of different classes, even
though you wrote neither of them for `FastStage`.

??? example "The whole script"

    ```{.python}
    --8<-- "docs/tutorials/device_protocols.py"
    ```

## What you built

You built a session with two stages of different classes, which the
presenter and view you already had both show and move. The script also passes
the type checker. From now on, each stage you add takes a line in the session
and a link, and no new presenter or view.

## Next steps

- [Building controls for a plan](plan-controls.md) is the next tutorial,
  where you write a plan and the window gains the controls to run it.
- [Questions](../explanation/questions.md) explains how a component matches a
  protocol, and how presenters and views are asked for in the same way.
- [Write a component](../how-to/write-a-component.md) has more detail on each
  kind of component.
