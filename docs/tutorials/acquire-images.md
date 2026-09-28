---
icon: lucide/camera
---

# Acquiring images

In this tutorial you add a camera to the session, and a presenter that offers
a plan to acquire with it. You find the frames on disk, and show the last one
in the window. It continues from
[Building controls for a plan](plan-controls.md).

The camera is a simulated one that ships with
[`ophyd-async`](../explanation/glossary.md#ophyd-async), so you need no
hardware and write no device. The presenter and the view of the plans stay as
they are: the session passes them the new plan.

## Before you start

!!! note "What you need"

    `h5py`, which the camera writes its file with and the session reads it
    with. It does not come with `redsun`:

    ```bash
    uv add h5py
    ```

Open `first_session.py`, and add these imports to the ones it has:

```python
from urllib.parse import urlsplit
from urllib.request import url2pathname

import bluesky.plans as bp
import h5py
import numpy as np
from bluesky.protocols import Readable, Triggerable
from event_model import DocumentRouter, StreamResource
from ophyd_async.sim import SimBlobDetector
from qtpy.QtGui import QImage, QPixmap
```

Nothing you wrote so far changes in this tutorial either.

## 1. Say what a camera is

A plan says what it needs from a device, as the plan of the stages did. Add a
second protocol below `HasPosition`:

```{.python}
--8<-- "docs/tutorials/acquire_images.py:camera"
```

A camera is a device that can be read and triggered. Both protocols come from
[`bluesky`](../explanation/glossary.md#bluesky). The stages can be read and
not triggered, so they are not cameras.

## 2. Offer a plan for it

Add a presenter below `PlanView`:

```{.python}
--8<-- "docs/tutorials/acquire_images.py:camera_ctrl"
```

It does two things.

It offers a plan, as `StagePlans` does. `snap` wraps
[`count`][bluesky.plans.count], a plan `bluesky` already has.

It follows the plan while it runs. The
[`RunEngine`][redsun.engine.RunEngine] describes what happens in
[documents](../explanation/glossary.md#document), and a `DocumentRouter`
receives each kind in a method of its name. This one listens for
[`StreamResource`](../explanation/glossary.md#streamresource), in which a
camera says which file it wrote. `show_last` opens that file and sends the
last frame with `sig_frame`.

## 3. Run it

Add the camera and the presenter to the session, as highlighted. A device
that already exists needs no code, only its line:

```{.python hl_lines="4 8"}
class FirstSession(QtSession):
    stage: AsDevice[MyStage]
    fast_stage: AsDevice[FastStage]
    camera: AsDevice[SimBlobDetector]
    stage_ctrl: AsPresenter[StagePresenter]
    stage_plans: AsPresenter[StagePlans]
    plan_ctrl: AsPresenter[PlanPresenter]
    camera_ctrl: AsPresenter[CameraPresenter]
```

Run the script:

```bash
uv run first_session.py
```

```text
Container built: 3/3 devices, 4/4 presenters, 2/2 views
```

The list of the plans has a second entry, `snap`. Choose it: the view shows
the plan widget of `snap`, with a list that holds `camera` and an input for
`frames`. You connected nothing: `CameraPresenter`
offers a plan, so the session passed it to `PlanPresenter` and to `PlanView`.
It reads documents, so the session passed it to `PlanPresenter` a second time,
among `callbacks`.

Press **Run**: the view greys out and comes back. The frames are acquired, and
nothing shows them yet. Close the window.

## 4. Show the frame

Add a view below `CameraPresenter`:

```{.python}
--8<-- "docs/tutorials/acquire_images.py:image_view"
```

`show_frame` turns the frame into an image, and stretches its values over the
whole scale of greys first, since the camera writes small numbers.

## 5. Add it to the session

Add the highlighted lines. You already have the first two:

```{.python hl_lines="4 8 11 19-22"}
--8<-- "docs/tutorials/acquire_images.py:session"
```

The first two links reach the
[path provider](../explanation/glossary.md#path-provider) of the session,
[`self.path_provider`][redsun.Session.path_provider], which tells the camera
where to write.
[`set_plan`][redsun.path_provider.SessionPathProvider.set_plan] gives it the
name of the plan that is about to run, and
[`reset_plan`][redsun.path_provider.SessionPathProvider.reset_plan] clears it
afterwards.

## 6. Acquire

```bash
uv run first_session.py
```

```text
Container built: 3/3 devices, 4/4 presenters, 3/3 views
```

Choose `snap` in the list of the plans and press **Run**. After a moment the
last frame appears:

![The window of the session: the rows of the stages on the left, and on the
right the plan widget of snap, chosen in the list of plans, above an image
of concentric rings](images/acquire-images.png)

## 7. Find the files

The frames are in the folder `redsun` keeps for you, under the name of the
session and the date:

```text
redsun/
`-- first-session/           the name session.yaml gives the session
    `-- 2026-09-28/          the day of the acquisition
        `-- camera/
            `-- snap_00000.h5
```

| Platform | Where `redsun/` is |
| --- | --- |
| Windows | `%LOCALAPPDATA%\redsun` |
| macOS | `~/Library/Application Support/redsun` |
| Linux | `~/.local/share/redsun` |

Open the folder, then press **Run** again: `snap_00001.h5` appears beside the
first. The files are named after the plan. The one of step 3 is there too, as
`unknown_00000.h5`: the path provider had not been told the name of the plan.

The session chose the folder and the name, and created the folder. The camera
wrote the file, in the format it chose. `redsun` itself writes no acquisition
data.

??? example "The whole script"

    The script leaves out the `config` line of the first tutorial, which
    needs `session.yaml`. Without it the folder of the session is called
    `FirstSession`, after the class.

    ```{.python}
    --8<-- "docs/tutorials/acquire_images.py"
    ```

## What you built

A session with a camera beside its two stages, and a second plan to choose in
the view of the plans. Its plan widget acquires as many frames as you ask for,
the last one shows in the window, and every acquisition is a file of its own on
disk, in a folder named after the session and the day. The plan reached its
widget and the `RunEngine` without a line of yours joining them.

## Next steps

- [Scanning a stage with the camera](scan-plan.md) is the next tutorial: it
  adds a plan that uses a stage and the camera together.
- [Write a session file](../how-to/write-a-session-file.md) shows how to keep
  the files in another folder.
- [Components](../explanation/components.md#where-a-device-writes) explains
  how the path of a file is made.
- [How to keep a catalog of runs](../how-to/keep-a-catalog.md) makes the
  acquisitions searchable.
