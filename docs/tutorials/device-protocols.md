---
icon: lucide/shapes
---

# Describing a device with a protocol

In this tutorial you make the presenter of the first session say what it needs
from a stage. A type checker can then follow the code, and another stage can
take the place of the first. It takes about ten minutes, and continues from
[Writing your first session](first-session.md).

You will check the types of the script, write a
[protocol](../explanation/glossary.md#protocol), ask the session for the
devices that satisfy it, and replace the stage without touching the presenter.

## Before you start

Open `first_session.py` as you left it at the end of the first tutorial.

You need a type checker. This tutorial uses
[`mypy`](https://mypy.readthedocs.io/). With `uv` there is nothing to install.
Without it, install `mypy` in the virtual environment of the first tutorial:

```bash
pip install mypy
```

## 1. Check the types

=== "uv"

    ```bash
    uv run --with mypy --with "redsun[pyqt]" mypy first_session.py
    ```

=== "pip"

    ```bash
    mypy first_session.py
    ```

The script runs, and still `mypy` finds two errors in it:

```text
first_session.py:39: error: "Device" has no attribute "position"  [attr-defined]
first_session.py:40: error: "Device" has no attribute "position"  [attr-defined]
Found 2 errors in 1 file (checked 1 source file)
```

The line numbers in your file may differ. The two lines are the ones in
`nudge` that read and set the position.

`devices` is a `DeviceMapping`: every device of the session, of any kind. All
the type checker knows about `devices["stage"]` is that it is a device, and
not every device has a position. An editor that checks types underlines the
same two lines, and has nothing to suggest after `self.stage.`.

## 2. Say what the presenter needs

The presenter needs one thing from a stage: a `position` it can read and set.
Write that down as a protocol, above the presenter:

```{.python}
--8<-- "docs/tutorials/device_protocols.py:protocol"
```

It needs two more imports:

```python
from typing import Protocol

from ophyd_async.core import SignalRW, StandardReadable, soft_signal_rw
```

`MyStage` does not inherit from `HasPosition`, and you do not change it. It
satisfies the protocol because it has a `position` of that type. This is
[structural subtyping](../explanation/glossary.md#structural-subtyping).

## 3. Ask for the devices that fit

Change the constructor of the presenter to ask for `DevicesOf[HasPosition]`
where it asked for `DeviceMapping`:

```{.python}
--8<-- "docs/tutorials/device_protocols.py:presenter"
```

In the import from `redsun`, replace `DeviceMapping` with `DevicesOf`.

The session passes the devices that satisfy `HasPosition`, by name, and leaves
the others out. `self.stage` is now a `HasPosition`, so the type checker knows
that `self.stage.position` holds a `float`.

## 4. Check the types again

Run the command of step 1 again:

```text
Success: no issues found in 1 source file
```

Then run the script. The window is the same, and **Nudge** moves the stage as
before.

## 5. Replace the stage

Add a second device below `MyStage`. It has a position, and a speed the first
one lacks:

```{.python}
--8<-- "docs/tutorials/device_protocols.py:device"
```

Use it in the session, by changing the class on the `stage` line:

```{.python}
--8<-- "docs/tutorials/device_protocols.py:session"
```

Check the types and run the script again. Both still work, and you did not
edit the presenter, because it names what it needs from a stage and not the
class of one.

??? example "The whole script"

    ```{.python}
    --8<-- "docs/tutorials/device_protocols.py"
    ```

## What you learned

- A `DeviceMapping` holds devices of any kind, so a type checker cannot tell
  what one of them has.
- A protocol lists what a component needs from a device, and a device
  satisfies it by having those members.
- `DevicesOf` asks the session for the devices that satisfy a protocol, with
  their type known.
- A presenter that asks for a protocol works with every device that
  satisfies it, whatever its class.

## Next steps

- [Questions](../explanation/questions.md) explains how a component matches a
  protocol, and how presenters and views are asked for in the same way.
- [Write a component](../how-to/write-a-component.md) has more detail on each
  kind of component.
