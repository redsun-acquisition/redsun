---
icon: lucide/play
---

# Writing your first session

In this tutorial you build a small application: a simulated motor stage, a
button that moves it, and a label that shows where it is. It takes about
fifteen minutes, and needs no hardware.

You will write the three kinds of
[component](../reference/glossary.md#component), put them in a
[session](../reference/glossary.md#session), and connect them.

## Before you start

Make an empty file called `first_session.py`. If you run scripts with
[`uv`](https://docs.astral.sh/uv/), start it with these lines, which tell `uv`
what the script needs so it installs them itself
([PEP 723](https://peps.python.org/pep-0723/)):

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["redsun[pyqt]>=0.14"]
# ///
```

Without `uv`, install `redsun` with a Qt binding instead:

```bash
pip install "redsun[pyqt]"
```

Everything below goes in the file, after these imports:

```python
from ophyd_async.core import StandardReadable, soft_signal_rw
from psygnal import Signal
from qtpy.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from redsun import AsDevice, AsPresenter, AsView, DeviceMapping, Placement, slot
from redsun.qt import Dock, QtSession
```

## 1. The device

A [device](../reference/glossary.md#device) describes one part of your setup:
here, a stage with a position. In a lab, a
[service](../reference/glossary.md#service) would reach the real hardware for
it. You have no hardware, so this one keeps its position in memory, using a
"soft" signal from `ophyd-async`:

```python
--8<-- "docs/tutorials/first_session.py:device"
```

A real stage would replace `soft_signal_rw` with signals a service provides.
Nothing else in this tutorial would change.

## 2. The presenter

A [presenter](../reference/glossary.md#presenter) holds the behaviour. This
one moves the stage by one step, and announces where it went:

```python
--8<-- "docs/tutorials/first_session.py:presenter"
```

Look at the constructor. You never call it yourself: the session does. It
passes the component's `name`, and finds a value for every other parameter:

- `devices` has the type `DeviceMapping`, so the session passes all its
  devices, by name.
- `step` has a default, so it is `1.0` unless you say otherwise.

`sig_moved` is a [signal](../reference/glossary.md#signal): the presenter
sends it, and does not care who listens. `nudge` is a
[slot](../reference/glossary.md#slot): something another component can
trigger.

## 3. The view

A [view](../reference/glossary.md#view) is what the user sees. This one is a
button and a label:

```python
--8<-- "docs/tutorials/first_session.py:view"
```

`placement` says where the view goes: docked on the left of the window. The
constructor takes `name` and `parent`, which every Qt view must.

Notice that the view knows nothing about the presenter, and the presenter
knows nothing about the view. Each only has signals and slots.

## 4. The session

Now put the three together:

```python
--8<-- "docs/tutorials/first_session.py:session"
```

Each line in the class body is a component. The name on the left, `stage`, is
the component's name; that is why the presenter finds it as
`devices["stage"]`. The part on the right says its
[layer](../reference/glossary.md#layer) and its class.

`wire` connects the pieces: pressing the button nudges the stage, and the
stage's new position reaches the label.

## 5. Run it

=== "uv"

    ```bash
    uv run first_session.py
    ```

=== "pip"

    ```bash
    python first_session.py
    ```

A window opens with the view docked on the left:

![The first session's window, with a Nudge button and a position label](images/first-session.png)

Press **Nudge**: the label counts up by one each time.

??? example "The whole script"

    ```python
    --8<-- "docs/tutorials/first_session.py"
    ```

## 6. Change a setting without touching the code

Make a file called `session.yaml` beside the script:

```yaml
session: first-session

presenters:
  stage_ctrl:
    step: 0.5
```

Tell the session to read it, by adding one line to the class:

```python
class FirstSession(QtSession):
    config = "session.yaml"
    ...
```

Run it again. Each press now moves the stage by `0.5`: the session found
`step` in the file and passed it to the presenter's constructor.

## What you learned

- A device talks to hardware, a presenter holds the behaviour, a view shows
  it.
- Components never create each other. The session makes them, and fills
  their constructors by name, by type, or from the session file.
- Components talk through signals and slots, and the session decides who is
  connected to whom.

## Next steps

- [Write a component](../how-to/write-a-component.md) has more detail on each
  kind.
- [Sessions](../explanation/session.md) explains what happens when a session
  builds.
- [Write a session file](../how-to/write-a-session-file.md) lists everything
  a file can say.
