---
icon: lucide/play
---

# Writing your first session

In this tutorial you build a small application: a simulated motor stage, a
button that moves it, and a label that shows where it is. It needs no
hardware, and it continues from [Installation](installation.md).

First you show the stage in a window, and then you make the button move it.
Along the way you write one of each of the three kinds of
[component](../explanation/glossary.md#component), and the
[session](../explanation/glossary.md#session) that makes them and holds them
together.

## Before you start

!!! note "What you need"

    The project folder of [Installation](installation.md), and nothing else.

In the project folder, make an empty file called `first_session.py`. Start it
with these imports:

```python
from __future__ import annotations

from collections.abc import Iterator
from functools import cached_property

from bluesky.protocols import Reading
from ophyd_async.core import (
    MovableLogic,
    StandardMovable,
    StandardReadable,
    soft_signal_rw,
)
from psygnal import Signal
from qtpy.QtWidgets import QFormLayout, QLabel, QPushButton, QWidget

from redsun import AsDevice, AsPresenter, AsView, DeviceMapping, Link, Placement, slot
from redsun.qt import Dock, QtSession
```

## 1. The device

A [device](../explanation/glossary.md#device) describes one part of your
setup, which here is a stage with a position. Since you have no hardware,
this stage keeps its position in memory. Add it below the imports:

```{.python}
--8<-- "docs/tutorials/first_session.py:device"
```

[`StandardReadable`][ophyd_async.core.StandardReadable] and
[`soft_signal_rw`][ophyd_async.core.soft_signal_rw] come from
[`ophyd-async`](../explanation/glossary.md#ophyd-async), the library `redsun`
uses for devices. `soft_signal_rw` makes a
[device signal](../explanation/glossary.md#device-signal) that keeps its value
in memory.

With `StandardReadable` alone, the stage would only be a value you can read
and write. [`StandardMovable`][ophyd_async.core.StandardMovable] turns it into
something that moves. Its `movable_logic` names two signals: the setpoint,
which you write to move the stage, and the readback, which says where the
stage is. This stage uses one signal for both. In return, the stage answers
the same methods as every motor in `ophyd-async`:

- `set` moves it, and finishes when the move does;
- `locate` says where it was sent and where it is;
- `stop` stops it, and `subscribe` follows its position.

Code that calls those methods, rather than an attribute called `position`,
works with this stage and with any real motor you put in its place. That
includes `bluesky` plans that move a device, and the positioner `redsun`
offers, which [the last tutorial](builtin-positioner.md) uses without changing
the stage.

A movable device reads its readback under its own name, so you read the
position of `stage` as `stage`.

## 2. The view

A [view](../explanation/glossary.md#view) is the part of the application the
user sees. Add this one below `MyStage`. For each stage it hears from, it
draws a row with a button and a label:

```{.python}
--8<-- "docs/tutorials/first_session.py:view"
```

`placement` says where the view goes, which here is docked on the left of the
window. `sig_nudge` is a [signal](../explanation/glossary.md#signal): when you
press a stage's button, the view sends it with the name of that stage.
`show_reading` is a [slot](../explanation/glossary.md#slot), a method
something else can trigger. It receives a reading, which is the value of a
device signal under the name of that signal. For the position of a stage,
that name is the name of the stage.

You never call the constructor yourself, because the session does it for
you. The session gives every view its `name` and its `parent`, and every
component keeps its name.

## 3. The session

Add a session below the view. For now it holds the stage and the view, and
sends the position of the stage to the view:

```python
class FirstSession(QtSession):
    stage: AsDevice[MyStage]
    stage_view: AsView[StageView]

    def wire(self) -> Iterator[Link]:
        yield self.stage.position, self.stage_view.show_reading


if __name__ == "__main__":
    FirstSession().run()
```

Each line in the class body declares a component, with its name on the left
and its [layer](../explanation/glossary.md#layer) and class on the right.
[`wire`][redsun.Session.wire] yields the
[links](../explanation/glossary.md#link) of the session, each one written as
what sends, then the slot that receives.

Run the script:

```bash
uv run first_session.py
```

The terminal tells you what the session built:

```text
Session built: 1/1 devices, 0/0 presenters, 1/1 views
```

In your terminal, the line starts with the time and the word `INFO`, which
these pages leave out.

A window opens with the view docked on the left:

![The first session's window, with a row for the stage: a Nudge button and
its position](images/first-session.png)

The view has one row, for `stage`. That row is there because a link from a
device signal sends the value the signal has now, and then every new one, so
the view heard from the stage as soon as the window opened. Press the button:
nothing happens yet, since nothing listens to it. Close the window.

## 4. The presenter

A [presenter](../explanation/glossary.md#presenter) holds what the
application does. Add this one between `MyStage` and `StageView`. It moves a
stage by one step:

```{.python}
--8<-- "docs/tutorials/first_session.py:presenter"
```

The session finds a value for each parameter of the constructor. Because
`devices` is a [`DeviceMapping`][redsun.DeviceMapping], it receives every
device of the session, by name. [Components](../explanation/components.md)
explains the rules the session follows.

`nudge` is a slot that takes the name of a stage. It's `async` because a
device takes time to answer.

!!! note

    An editor that checks types underlines the two lines of `nudge`.
    `devices` holds devices of every kind, so the editor can't tell that this
    one has a position. The script runs all the same, and
    [Describing a device with a protocol](device-protocols.md) fixes it.

## 5. Connect them

Add the highlighted lines to the session. They declare the presenter, and add
the link that sends each press of a button to it:

```{.python hl_lines="3 7"}
--8<-- "docs/tutorials/first_session.py:session"
```

The view knows nothing about the presenter, and the presenter knows nothing
about the view, so it's the session that joins them. A presenter and a view
written to be joined this way are called a
[stack](../explanation/glossary.md#stack).

Run the script again:

```bash
uv run first_session.py
```

```text
Session built: 1/1 devices, 1/1 presenters, 1/1 views
```

Press the button: the position counts up by one each time.

## 6. Change a setting without touching the code

Make a file called `session.yaml` in the project folder, beside the script:

```yaml
session: first-session

presenters:
  stage_ctrl:
    step: 0.5
```

The first line gives the session a name, and the rest gives a value to the
`step` parameter of the `stage_ctrl` component.

To tell the session to read the file, add this line to the class
`FirstSession`, as its first line:

```python
config = "session.yaml"
```

Run the script again. Each press now moves the stage by `0.5`, because the
session found `step` in the file and passed it to the presenter's
constructor.

The session looks for the file in the folder you run the command from, which
is the project folder. Keep both the file and the line, since the next
tutorials count on them.

??? example "The whole script"

    The script leaves out the `config` line of step 6.

    ```{.python}
    --8<-- "docs/tutorials/first_session.py"
    ```

## What you built

You built a window that shows a simulated stage and moves it. It's made of a
device, a presenter and a view, which a session built and connected for you.
The size of each step comes from a file you can change without opening the
script.

## Next steps

- [Describing a device with a protocol](device-protocols.md) is the next
  tutorial, where you add a second stage that the same presenter and view
  control.
- [Write a component](../how-to/write-a-component.md) has more detail on each
  kind of component.
- [Sessions](../explanation/session.md) explains what happens when a session
  builds.
- [Write a session file](../how-to/write-a-session-file.md) lists everything
  a file can say.
