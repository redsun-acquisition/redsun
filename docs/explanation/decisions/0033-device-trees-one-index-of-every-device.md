# 33. Device trees: one index of every device

Date: 2026-10-24

## Status

Accepted

## Context

`ophyd-async` describes a setup as a tree. One root device holds the stages,
cameras and lights as its children, and their signals sit below them. Before
this record, most of `redsun` saw only the devices a session declared, so a
session declaring one `MyMicroscope` got no stage in its
[positioner](0020-a-built-in-positioner.md), no light in its light view and no
camera to offer its plans. [`DeviceMapping`][redsun.DeviceMapping] and
[`DevicesOf`][redsun.DevicesOf] held the declared devices and nothing below
them. So the docs asked you to declare each piece a plan or a view needs as a
device of its own.

Reading the trees meant deciding which devices answer a question about
devices, what names they go by, how a view shows a device that sits deep in a
tree, and what a plan holds when it locks a device.

## Decision

- **The session keeps one index of every device.** In the registry
  [build step](../glossary.md#build-step), the
  session lists each declared device and every device below it with
  `walk_devices` from `ophyd-async`, and keeps them all except signals and
  commands. A [device signal](../glossary.md#device-signal) is a device too,
  and so is a command, an action the device runs. `DeviceMapping` is that index,
  and `DevicesOf[P]` is the index filtered by `P`. Signals stay out because a
  writable signal has `set`, `locate` and `subscribe`, so with them in, a
  motor's velocity would answer a question about axes. Commands stay out for
  the same reason. The index is built after connecting, because some
  transports create children only while they connect.
- **Devices keep the names `ophyd-async` gives them.** The stage `xy` of
  `microscope` is `microscope-xy`, the name the run's documents also use.
  No code finds a device or its owner by splitting a name at `-`, since a name
  may hold a dash of its own and the separator can be changed. Two devices
  with one name, or a device with no name, stop the build with a
  [`BuildError`][redsun.errors.BuildError].
- **Each device answers for itself.** `DevicesOf[P]` checks every device
  against `P`, and a device's parent or children play no part in its answer.
  So a root and its children can all match. A `DeviceMap` is the
  `ophyd-async` container that holds devices by key, and it matches only if
  it satisfies `P` itself. A map of lights is not a light, so
  `DevicesOf[Light]` holds the lights and not the map.
- **The positioner groups axes by the device holding them.** An axis is a row
  of the box of its direct parent, under the name the parent gives it. An axis
  with no parent is a box of its own, and an axis below another axis is left
  out, as before.
- **A lock reaches down, never up.** A plan that locks a device holds it and
  every device below it, and no device above it. A plan moving the stage's `x`
  disables the `x` row and leaves the `y` row free. Presenters check a device
  with [`held_by`][redsun.utils.devices.held_by], and views apply the same
  rule to the paths the presenters send them.
- **A view shows a device by its root and path.**
  [`device_path`][redsun.utils.devices.device_path] returns a
  [`DevicePath`][redsun.utils.devices.DevicePath], which reads as
  `microscope / xy.x`. The descriptions
  presenters send carry it in new fields that have defaults: `AxisInfo.path`,
  `LightInfo.path`, `Configuration.paths` and `ParamDescription.labels`. A view
  titles a box with the path and gives it the device's name as its tooltip.
- **`Session.devices` keeps meaning the declared devices** that built, since
  the build summary counts them.

### Before

The same setup, declared as one root device:

```python
class MyMicroscope(StandardReadable):
    def __init__(self, name: str = "") -> None:
        self.xy = MyStage()
        self.camera = MyCamera()
        super().__init__(name=name)


class MyApp(QtSession):
    microscope: AsDevice[MyMicroscope]
```

A presenter asking for `DeviceMapping` received `microscope` alone, and the
positioner showed one box, `microscope`, holding every axis of the setup. To
see the stage and the camera as devices, you declared them one by one:

```python
class MyApp(QtSession):
    stage: AsDevice[MyStage]
    camera: AsDevice[MyCamera]
```

### After

The session declaring `microscope` holds every device of the tree:

```python
set(devices)
# {"microscope", "microscope-xy", "microscope-xy-x", "microscope-xy-y",
#  "microscope-camera"}, and the camera's own devices
```

The positioner shows the box `microscope / xy` with the rows `x` and `y`,
and a plan whose parameter takes a camera is offered `microscope / camera`.
The session that declares `stage` and `camera` one by one keeps working, and
now also holds `stage-x` and `stage-y`.

Other options were rejected:

- Letting each component walk the trees itself. Every built-in and every
  plugin would repeat the walk and the name checks, and they could disagree on
  what a session holds.
- One positioner box per declared device. A root holding the whole setup would
  be one box with every axis in it.
- Locks reaching up as well as down. Moving one axis would lock the whole
  microscope in the window.
- Changing `Session.devices` to the index. It is public, and it means what the
  session declared.
- New types for `Configuration.owners` and `ParamDescription.choices` in place
  of new fields. Presenters and views written for 0.15 would break.

## Consequences

- A session declaring devices one by one sees more devices too: their
  children are now in `DeviceMapping` and among the choices of a plan
  parameter they match. No name disappears.
- A device whose axes sit deeper than its own children moves them to another
  box: a stage holding its axes in `stage.motors` shows them in the box
  `stage / motors`, so positions saved under `stage` no longer match. The
  [migration page](../../how-to/migrate-from-0.15.md) says to save them again;
  no converter is written.
- `find_axes` and `walk_axes` are removed. They gathered every axis below one
  device for one box, which the positioner no longer does.
- Children declared with annotations, in the `ophyd-async` style, are created
  by the device's connector, the `ophyd-async` object that connects it over
  its transport, such as EPICS. `redsun` reads the tree once it is built.
  A connector that adds children without naming them stops the build.
- A root device takes the [prefix](../glossary.md#prefix) of one service. Pieces that sit behind
  different services are still declared one by one.
- A custom view written for 0.15 keeps working, and shows names where the new
  fields would give paths.
