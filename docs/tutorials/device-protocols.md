---
icon: lucide/shapes
---

# Describing a device with a protocol

In this tutorial you add a second stage to the session, of another class. The
presenter and the view you wrote control it too, and you edit two lines of
the first and none of the second. It continues from
[Writing your first session](first-session.md).

You will check the types of the script, write a
[protocol](../explanation/glossary.md#protocol), ask the session for the
devices that satisfy it, and add the stage.

## Before you start

!!! note "What you need"

    A type checker. This tutorial uses
    [`mypy`](https://mypy.readthedocs.io/), which does not come with
    `redsun`. Add it to the project as a tool for development:

    ```bash
    uv add --dev mypy
    ```

Open `first_session.py` as you left it at the end of the first tutorial. You
keep working in this file until the last tutorial. Each one adds to what is
there, and where a line you wrote has to change, the page shows it
highlighted.

## 1. Check the types

```bash
uv run mypy first_session.py
```

The script runs, and still `mypy` finds two errors in it:

```text
first_session.py:27: error: "Device" has no attribute "position"  [attr-defined]
first_session.py:28: error: "Device" has no attribute "position"  [attr-defined]
Found 2 errors in 1 file (checked 1 source file)
```

The line numbers in your file may differ. The two lines are the ones in
`nudge` that read and set the position.

`devices` is a [`DeviceMapping`][redsun.DeviceMapping]: every device of the
session, of any kind. All the type checker knows about one of them is that it
is a device, and not every device has a position.

## 2. Say what the presenter needs

The presenter needs one thing from a stage: a `position` it can read and set.
Write that down as a protocol, above `StagePresenter`:

```{.python}
--8<-- "docs/tutorials/device_protocols.py:protocol"
```

Add the imports it needs to the ones at the top of the file:

```python
from typing import Protocol, runtime_checkable

from ophyd_async.core import SignalRW
```

`MyStage` does not inherit from `HasPosition`, and you do not change it. It
satisfies the protocol because it has a `position` of that type. This is
[structural subtyping](../explanation/glossary.md#structural-subtyping).
[`runtime_checkable`][typing.runtime_checkable] allows the same check while
the program runs, which the next tutorial relies on.

## 3. Ask for the devices that fit

Change the constructor of `StagePresenter` as highlighted. It asks for
[`DevicesOf[HasPosition]`][redsun.DevicesOf] under the name `stages`, where it
asked for a `DeviceMapping` under the name `devices`:

```{.python hl_lines="1-3 5"}
--8<-- "docs/tutorials/device_protocols.py:constructor"
```

Add one more import:

```python
from redsun import DevicesOf
```

The session now passes the devices that satisfy `HasPosition`, by name, and
leaves the others out.

!!! tip "Imports on more than one line"

    The file now imports from `redsun` on two lines, which Python allows.
    The whole script at the end of each page gathers such lines into one, as
    a formatter would. It also drops the import of `DeviceMapping`, which
    nothing uses for now. Leave it in your file: a later tutorial needs it
    again.

## 4. Check the types again

```bash
uv run mypy first_session.py
```

```text
Success: no issues found in 1 source file
```

Run the script. The window is the same, and the button moves the stage as
before:

```bash
uv run first_session.py
```

## 5. Add a second stage

Add a second device below `MyStage`. It starts at `5.0`, and has a speed the
first one lacks:

```{.python}
--8<-- "docs/tutorials/device_protocols.py:device"
```

`FastStage` shares no code with `MyStage`, and does not mention `HasPosition`.
It satisfies the protocol all the same.

## 6. Add it to the session

Add the highlighted lines to the session: the stage, and the link that sends
its position to the view.

```{.python hl_lines="3 10"}
--8<-- "docs/tutorials/device_protocols.py:session"
```

Check the types, then run the script:

```bash
uv run mypy first_session.py
uv run first_session.py
```

```text
Container built: 2/2 devices, 1/1 presenters, 1/1 views
```

![The window of the session, with a row for each stage: a Nudge button and a
position](images/device-protocols.png)

The view has a second row, for `fast_stage`, which starts at `5.0`. Press its
button: `fast_stage` moves, and `stage` stays where it is.

One presenter and one view now control two stages of different classes. You
wrote neither of them for `FastStage`.

??? example "The whole script"

    ```{.python}
    --8<-- "docs/tutorials/device_protocols.py"
    ```

## What you built

A session with two stages of different classes, both shown and moved by the
presenter and the view of the first tutorial. The script passes the type
checker. Every stage you add in the next tutorials takes a line in the
session and a link, and no new presenter or view.

## Next steps

- [Building controls for a plan](plan-controls.md) is the next tutorial: you
  write a plan, and the window gains the controls to run it.
- [Questions](../explanation/questions.md) explains how a component matches a
  protocol, and how presenters and views are asked for in the same way.
- [Write a component](../how-to/write-a-component.md) has more detail on each
  kind of component.
