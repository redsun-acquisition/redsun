---
icon: lucide/camera
---

# Acquiring images

In this tutorial you add a camera to the session, and a presenter that offers
a plan to acquire with it. You then find the frames on disk, and show the
last one in the window. It continues from
[Building controls for a plan](plan-controls.md).

The camera is a simulated one that ships with
[`ophyd-async`](../explanation/glossary.md#ophyd-async), so you need no
hardware and don't write a device. The presenter and the view of the plans
stay as they are, because the session passes them the new plan.

## Before you start

!!! note "What you need"

    `h5py`, which the camera uses to write its file and the session uses to
    read it. It doesn't come with `redsun`:

    ```bash
    uv add h5py
    ```

    `h5py` comes without information on its types, and `mypy` reports that
    as an error. If you keep checking the types of the script, add these
    lines to `pyproject.toml` first:

    ```toml
    [tool.mypy]
    disable_error_code = ["import-untyped"]
    ```

Open `first_session.py`, and add these imports below the ones it has:

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

Nothing you've written so far changes in this tutorial either.

## 1. Say what a camera is

Like `walk`, the new plan says what it needs from a device with a protocol.
Add a second protocol below `HasPosition`:

```{.python}
--8<-- "docs/tutorials/acquire_images.py:camera"
```

A camera is a device you can read, and trigger to take a frame. Both
protocols come from [`bluesky`](../explanation/glossary.md#bluesky). You can
read the stages but not trigger them, so they aren't cameras.

## 2. Offer a plan for it

Add a presenter below `PlanView`:

```{.python}
--8<-- "docs/tutorials/acquire_images.py:camera_ctrl"
```

It offers a plan, as `StagePlans` does. The plan, `snap`, wraps
[`count`][bluesky.plans.count], a plan `bluesky` already has.

The presenter also follows the plan as it goes. The
[`RunEngine`][redsun.engine.RunEngine] emits
[documents](../explanation/glossary.md#document), records of what happens,
and a `DocumentRouter` such as this presenter gets each kind in a method of
the same name. This one handles
[`StreamResource`](../explanation/glossary.md#streamresource), which a device
emits to say which file it wrote. The camera emits two in a run, and the one
named `camera` holds its frames. Once the plan has ended,
`show_last` turns the URI of that file into a path with the two functions of
`urllib`, opens the file, and sends the last frame with `sig_frame`.

## 3. Run it

Add these two lines to the session, the first among the devices and the
second among the presenters. A device someone else already wrote needs no
code from you, only its line:

```python
camera: AsDevice[SimBlobDetector]
camera_ctrl: AsPresenter[CameraPresenter]
```

Run the script:

```bash
uv run first_session.py
```

```text
Session built: 3/3 devices, 4/4 presenters, 2/2 views
```

The list of the plans has a second entry, `snap`. Choose it, and the view
shows the plan widget of `snap`, with a list that holds `camera` and an input
for `frames`. You didn't connect anything. Because `CameraPresenter` offers a
plan, the session passed it to `PlanPresenter` and to `PlanView`. Because
it's also a `DocumentRouter`, the session passed it to `PlanPresenter` a
second time, among `callbacks`.

Press **Run**: the view greys out and comes back. The camera acquires the
frames, but nothing shows them yet. Close the window.

## 4. Show the frame

Add a view below `CameraPresenter`:

```{.python}
--8<-- "docs/tutorials/acquire_images.py:image_view"
```

`show_frame` turns the frame into an image. Since the camera writes small
numbers, it first stretches the values over the whole scale of greys.

## 5. Add it to the session

Add the highlighted lines. You already added the first two in step 3:

```{.python hl_lines="5 9 12 20-23"}
--8<-- "docs/tutorials/acquire_images.py:session"
```

The first two new links reach the
[path provider](../explanation/glossary.md#path-provider) of the session,
[`self.path_provider`][redsun.Session.path_provider], which tells the camera
where to write.
[`set_plan`][redsun.path_provider.SessionPathProvider.set_plan] gives the
path provider the name of the plan that's about to run, and
[`reset_plan`][redsun.path_provider.SessionPathProvider.reset_plan] clears it
afterwards.

## 6. Acquire

```bash
uv run first_session.py
```

```text
Session built: 3/3 devices, 4/4 presenters, 3/3 views
```

Choose `snap` in the list of the plans and press **Run**. After a moment the
last frame appears:

![The window of the session: the rows of the stages on the left, and on the
right the plan widget of snap, chosen in the list of plans, above an image of
concentric rings](images/acquire-images.png)

## 7. Find the files

The frames are in the folder `redsun` keeps for you, in folders named after
the session and the date:

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
first. The files are named after the plan. The file from step 3 is
there too, as `unknown_00000.h5`, because nothing had told the path provider
the name of the plan yet.

The session chose the folder and the name, and created the folder. The camera
wrote the file, in a format it chose. `redsun` itself writes no acquisition
data.

??? example "The whole script"

    ```{.python}
    --8<-- "docs/tutorials/acquire_images.py"
    ```

## What you built

You added a camera beside the two stages, and a second plan to choose in the
view of the plans. Its plan widget acquires as many frames as you ask for,
and the last one shows in the window. Every acquisition is a file of its own
on disk, in a folder named after the session and the day. The plan reached
its widget and the `RunEngine` without a line of yours joining them.

## Next steps

- [Scanning a stage with the camera](scan-plan.md) is the next tutorial,
  where you add a plan that uses a stage and the camera together.
- [How to choose where acquisition files go](../how-to/choose-where-files-go.md)
  shows how to keep the files in another folder.
- [Components](../explanation/components.md#where-a-device-writes) explains
  how the path of a file is made.
- [How to keep a catalog of runs](../how-to/keep-a-catalog.md) makes the
  acquisitions searchable.
