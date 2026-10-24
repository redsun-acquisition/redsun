---
icon: lucide/video
---

# How to write a camera for continuous acquisition

In [continuous acquisition](../explanation/glossary.md#continuous-acquisition),
a camera takes frames one after another whether or not a plan runs, so a live
view can show them at any time. On this page you write such a camera as an
`ophyd-async` [device](../explanation/glossary.md#device), and plans read its
latest frame into their events or write its frames to a file without stopping
the acquisition. The plans that read are those of `bluesky`, and the one that
writes is a few lines you add. The last section does the same for a camera
served by an [areaDetector](../explanation/glossary.md#areadetector)
[IOC](../explanation/glossary.md#ioc).

## Prerequisites

You need a [service](../explanation/glossary.md#service) that runs the camera,
and [How to write a service](write-a-service.md) shows how to write one and
declare it. The device on this page expects the service to serve these
[process variables](../explanation/glossary.md#process-variable) under its
[prefix](../explanation/glossary.md#prefix), over
[PVAccess](../explanation/glossary.md#pvaccess):

| Process variable | Holds |
| --- | --- |
| `Acquire` | `true` while the camera acquires. A write to it completes at once, without waiting for the acquisition to end. |
| `Exposure` | The exposure time, in seconds. |
| `Image` | The latest frame, as an `NTNDArray`. It holds a frame of the right shape from the start. |
| `ImageCount` | The number of frames taken so far. It goes up by one each time `Image` changes. |
| `Capture` | `true` while frames go to the file. The service sets it back to `false` after `NumCapture` frames. |
| `NumCapture` | The number of frames to write, or 0 to write until `Capture` is set to `false`. |
| `FilePath` | The `file://` address of the next file. Writing it sets `NumCaptured` to 0. |
| `NumCaptured` | The number of frames written to the current file. |

The service writes the frames into the dataset `/data` of an HDF5 file.
PVAccess carries a frame together with its shape, which
[Channel Access](../explanation/glossary.md#channel-access) can't, so the
session speaks PVAccess; see
[Name the transport](write-a-service.md#name-the-transport).

## Write the camera

The camera reads the latest frame when a plan asks for one. A plan starts the
acquisition if it was stopped and leaves it as it found it, which a small
class does for the camera and, further down, for the writer:

```{.python}
--8<-- "docs/examples/continuous_camera.py:acquire-for-plan"
```

The camera itself reads the service's process variables:

```{.python}
--8<-- "docs/examples/continuous_camera.py:camera"
```

- `HINTED_UNCACHED_SIGNAL` makes `image` a
  [hint](../explanation/glossary.md#hint) of the camera, so a plan reads it and
  a live view finds it without knowing its name. `UNCACHED` makes each read
  ask the service for the frame, instead of returning the last value the
  device received.
- `CONFIG_SIGNAL` records the exposure time once, in the description of the
  [run](../explanation/glossary.md#run), so the events don't repeat it.
- `stage` and `unstage` are what a plan calls before and after it uses the
  camera; see [stage](../explanation/glossary.md#stage).
- `trigger` waits for the second frame after it is called. The first one may
  have started its exposure before the call, while a motor was still moving,
  so it could show the sample in the wrong place.

## Write the writer

The writer saves frames to a file while the acquisition goes on. It is an
`ophyd-async` `StandardDetector`, which takes three parts: one prepares the
number of frames, one starts and stops the capture, and one says where the
frames go:

```{.python}
--8<-- "docs/examples/continuous_camera.py:writer-logics"
```

- `CaptureTrigger` sets `NumCapture` to the number of frames the plan asks
  for.
- `CaptureAcquire` starts the acquisition when the writer is staged, and turns
  off a capture an earlier plan left on. It puts the acquisition back as it
  was when the writer is unstaged, through the same `AcquireForPlan`.
- `wait_for_idle` waits until the service has written the frames asked for, or
  stops the capture at once when none were asked for.
- `CaptureData` sets the file, then reads the shape and type of a frame from
  `image`, so the [documents](../explanation/glossary.md#document) of the
  run describe what the file holds. It tells
  `bluesky` the frames are in `/data` of an HDF5 file, and how many are
  written so far.

The writer builds the three parts from its own process variables:

```{.python}
--8<-- "docs/examples/continuous_camera.py:writer"
```

!!! warning "A writer inside the camera is never staged"

    The plans of `bluesky` stage the device at the top of the tree each
    device belongs to. A writer held as an attribute of the camera is never
    staged itself, so a second write reuses what the first one prepared and
    times out. Declare the writer as a device of its own.

## Declare them

Declare the camera and the writer beside the service, which gives both its
prefix:

```{.python}
--8<-- "docs/examples/continuous_camera.py:session"
```

`wire` links every hinted signal that holds an array to the live view, which
the next section writes.

## Show the frames live

A live view finds the frames through hints, so it works for any camera,
including one whose image signal has another name. The function below
returns the hinted signals of a device whose values are arrays:

```{.python}
--8<-- "docs/examples/continuous_camera.py:hinted-arrays"
```

The camera sends every frame it takes, and a screen needs far fewer, so the
[presenter](../explanation/glossary.md#presenter) passes a frame on only when
enough time has gone by since the last one of the same signal:

```{.python}
--8<-- "docs/examples/continuous_camera.py:live-frames"
```

A view connected to `sig_frame` gets the name of the signal and the frame.
Frames arrive only while the camera acquires. A plan starts the acquisition
for as long as it runs, and outside a plan you set `acquire`, for instance
from a button of a view of your own.

## Run plans

Plans of `bluesky` read the camera as they would any detector. Each one stages
the camera, so it leaves the acquisition as it found it:

| To | Run |
| --- | --- |
| Take frames in events | `bp.count([camera], num=3)` |
| Take a frame at each position of a motor | `bp.rel_scan([camera], motor, 0, 2, 3)` |
| Read the camera in a loop of your own | `bps.trigger_and_read([camera, motor])` inside `bpp.stage_wrapper(..., [camera])` |
| Write frames to a file only | `write_frames([camera_writer], 5)` |

`trigger_and_read` doesn't stage the camera, so a loop of your own needs the
`stage_wrapper` around it. `bluesky` has no plan that prepares a writer and
declares its stream before collecting, which `ophyd-async` requires, so
writing takes this plan:

```{.python}
--8<-- "docs/examples/continuous_camera.py:write-frames"
```

`collect_while_completing` sends the frames written so far every half
second, so a long write shows progress in the documents of the run.
`bp.fly` collects without declaring the stream first, and fails with
`Single nested data keys should be pre-declared`.

!!! warning "Stage a device inside the plan that uses it"

    Run as a plan of its own, `bps.stage(camera)` leaves the camera staged,
    and the [RunEngine](../explanation/glossary.md#runengine) unstages it when
    that plan ends without waiting for it to finish. The next plan then stages
    the camera while it is still being unstaged. Stage a device in the plan
    that uses it.

## Use an areaDetector camera

An areaDetector IOC already does what the service above does, and
`ophyd-async` drives one in continuous acquisition with `ContAcqDetector`. The
device is a subclass of it, with two additions.

!!! warning "Needs an `ophyd-async` release after 0.21.3"

    `ophyd-async` 0.21.3 never sends the trigger that lets frames through to
    the file, so every plan on this section's camera times out. This section
    was checked against the main branch of `ophyd-async` on 24 October 2026,
    before a release with the fix was out.

The IOC needs these plugins, under the names `ContAcqDetector` looks for:

- `cam1:`, the driver, which acquires in continuous mode.
- `CB1:`, a circular buffer fed by the driver, which holds frames back until
  a plan asks for them.
- `HDF1:`, an HDF5 writer fed by `CB1:`.
- `Pva1:`, which serves the latest frame of the driver over PVAccess as
  `Pva1:Image`.

The device reads `Pva1:Image` as its hinted signal, and starts the acquisition
when it is staged:

```{.python}
--8<-- "docs/examples/continuous_areadetector.py:camera"
```

- `PluginSignalDataLogic` adds `image` to what the camera reads and to its
  hints, so the plans and the live view above find it as they find the image
  of the other camera.
- The driver's `acquire` waits, by default, for the acquisition to end, which
  in continuous mode never happens. `set_and_wait_for_value` with
  `wait_for_set_completion=False` returns once the driver reports it is
  acquiring.
- `stage` starts the acquisition only when it was stopped, because a second
  start while the first is still waiting stalls the connection to the IOC;
  see the warning below.

Declare the IOC as an [attached service](../explanation/glossary.md#attached-service),
and link the hinted arrays to the live view as before:

```{.python}
--8<-- "docs/examples/continuous_areadetector.py:session"
```

The camera is its own writer, so `write_frames([camera], 5)` writes frames
during the acquisition, and `bp.count`, `bp.rel_scan` and the loop of the
table run as they do above. Each of them also writes the frames it reads to
the HDF5 file, since the camera always writes through `HDF1:`.

!!! warning "A second start stalls the connection"

    A Channel Access write that waits for its completion stays open until the
    IOC reports it complete, which a start in continuous mode never does.
    While one is open on a process variable, a second waiting write to the
    same one stops every reply on that connection, and the plans on the camera
    time out. Start the acquisition only when it is stopped, and stop it with
    `driver.acquire.set(False)`, which doesn't wait.

The frame travels over PVAccess and everything else over Channel Access. If
the IOC is on another network, the `address` you give `Attach` reaches Channel
Access only, so also list the IOC in `EPICS_PVA_ADDR_LIST`.

## The examples in full

??? example "The camera, the writer and the live view"

    ```{.python}
    --8<-- "docs/examples/continuous_camera.py"
    ```

??? example "The areaDetector camera"

    ```{.python}
    --8<-- "docs/examples/continuous_areadetector.py"
    ```
