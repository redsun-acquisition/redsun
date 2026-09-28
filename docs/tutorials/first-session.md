---
icon: lucide/play
---

# Writing your first session

In this tutorial you build a small application: a simulated motor stage, a
button that moves it, and a label that shows where it is. It needs no
hardware, and continues from [Installation](installation.md).

You will show the stage in a window first, then make the button move it. On
the way you write the three kinds of
[component](../explanation/glossary.md#component), and the
[session](../explanation/glossary.md#session) that holds them.

## Before you start

!!! note "What you need"

    The project folder of [Installation](installation.md), and nothing else.

In the project folder, make an empty file called `first_session.py`. Start it
with these imports:

```python
from __future__ import annotations

from collections.abc import Iterator

from bluesky.protocols import Reading
from ophyd_async.core import StandardReadable, soft_signal_rw
from psygnal import Signal
from qtpy.QtWidgets import QFormLayout, QLabel, QPushButton, QWidget

from redsun import AsDevice, AsPresenter, AsView, DeviceMapping, Link, Placement, slot
from redsun.qt import Dock, QtSession
```

## 1. The device

A [device](../explanation/glossary.md#device) describes one part of your setup:
here, a stage with a position. You have no hardware, so this one keeps its
position in memory. Add it below the imports:

```{.python}
--8<-- "docs/tutorials/first_session.py:device"
```

[`StandardReadable`][ophyd_async.core.StandardReadable] and
[`soft_signal_rw`][ophyd_async.core.soft_signal_rw] come from
[`ophyd-async`](../explanation/glossary.md#ophyd-async). The second makes a
[device signal](../explanation/glossary.md#device-signal) that keeps its value
in memory.

## 2. The view

A [view](../explanation/glossary.md#view) is what the user sees. Add this one
below `MyStage`. It draws a row for each stage it hears from, with a button
and a label:

```{.python}
--8<-- "docs/tutorials/first_session.py:view"
```

`placement` says where the view goes: docked on the left of the window.
`sig_nudge` is a [signal](../explanation/glossary.md#signal), which the view
sends with the name of a stage when its button is pressed. `show_reading` is a
[slot](../explanation/glossary.md#slot), which something else can trigger. It
receives a reading: the value of a device signal, under the name of that
signal.

## 3. The session

Add a session below the view. For now it holds the stage and the view, and
sends the position of the first to the second:

```python
class FirstSession(QtSession):
    stage: AsDevice[MyStage]
    stage_view: AsView[StageView]

    def wire(self) -> Iterator[Link]:
        yield self.stage.position, self.stage_view.show_reading


if __name__ == "__main__":
    FirstSession().run()
```

Run the script:

```bash
uv run first_session.py
```

The terminal says what the session built:

```text
Container built: 1/1 devices, 0/0 presenters, 1/1 views
```

and a window opens with the view docked on the left:

![The first session's window, with a row for the stage: a Nudge button and
its position](images/first-session.png)

The view has one row, for `stage`. Press the button: nothing happens yet,
since nobody listens to it. Close the window.

## 4. The presenter

A [presenter](../explanation/glossary.md#presenter) holds the behaviour. Add
this one between `MyStage` and `StageView`. It moves a stage by one step:

```{.python}
--8<-- "docs/tutorials/first_session.py:presenter"
```

You never call the constructor yourself: the session does, and finds a value
for each parameter. `devices` is a
[`DeviceMapping`][redsun.DeviceMapping], so it receives every device of the
session, by name. [Components](../explanation/components.md) explains the
rules.

`nudge` is a slot that takes the name of a stage. It is `async` because a
device takes time to answer.

!!! note

    An editor that checks types underlines the two lines of `nudge`.
    `devices` holds devices of every kind, so the editor cannot tell that
    this one has a position. The script runs all the same, and
    [Describing a device with a protocol](device-protocols.md) corrects it.

## 5. Connect them

Add the highlighted lines to the session: the presenter, and the link that
sends the press of a button to it.

```{.python hl_lines="3 7"}
--8<-- "docs/tutorials/first_session.py:session"
```

[`wire`][redsun.Session.wire] is where the session connects its components.
The view knows nothing about the presenter, and the presenter knows nothing
about the view.

Run the script again:

```bash
uv run first_session.py
```

```text
Container built: 1/1 devices, 1/1 presenters, 1/1 views
```

Press the button: the position counts up by one each time.

## 6. Change a setting without touching the code

Make a file called `session.yaml` beside the script:

```yaml
session: first-session

presenters:
  stage_ctrl:
    step: 0.5
```

Tell the session to read it, by adding the highlighted line to the class:

```{.python hl_lines="2"}
class FirstSession(QtSession):
    config = "session.yaml"
    stage: AsDevice[MyStage]
```

Run it again. Each press now moves the stage by `0.5`: the session found
`step` in the file and passed it to the presenter's constructor.

Keep the file and the line. The pages of the next tutorials do not show the
`config` line, and your session has it all the same.

??? example "The whole script"

    The script leaves out the `config` line of step 6, which needs
    `session.yaml`.

    ```{.python}
    --8<-- "docs/tutorials/first_session.py"
    ```

## What you built

A window that shows a simulated stage and moves it, made of a device, a
presenter and a view that a session built and connected. The step of the
stage comes from a file you can change without opening the script.

## Next steps

- [Describing a device with a protocol](device-protocols.md) is the next
  tutorial: it adds a second stage, which the same presenter and view
  control.
- [Write a component](../how-to/write-a-component.md) has more detail on each
  kind.
- [Sessions](../explanation/session.md) explains what happens when a session
  builds.
- [Write a session file](../how-to/write-a-session-file.md) lists everything
  a file can say.
