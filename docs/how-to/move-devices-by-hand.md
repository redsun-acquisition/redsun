---
icon: lucide/move
---

# How to move devices by hand

Add the built-in positioner to a session: a presenter that moves the axes of
your [devices](../explanation/glossary.md#device), and a view with a row per
axis to step it, send it to a position, stop it and change its settings.
[ADR 20](../explanation/decisions/0020-a-built-in-positioner.md) explains the
design.

## Prerequisites

Devices whose moving parts are `ophyd-async` movables, such as a
`StandardMovable` or an EPICS `Motor`. The Python blocks below are parts of
one script; the whole script is at the end.

## Which parts are axes

The positioner looks inside every device for its axes. An axis is a part that
`set` moves, `locate` reports and `subscribe` follows: it satisfies
`AsyncLocatable` from `ophyd-async` and `Subscribable` from `bluesky`, and it
is not a signal. The search stops at each axis it finds, so the signals of an
axis are never shown as axes. A device that is itself movable is its own
single axis.

Each axis is shown under its attribute name. This stage has two axes, `x` and
`y`:

```{.python}
--8<-- "docs/examples/positioner.py:device"
```

Axes are found by what they can do, never by their names, so the view makes
no assumption about which axis is which. [`find_axes`][redsun.utils.devices.find_axes]
returns what the positioner finds for a device.

## Declare the positioner in a session file

Both components are built into `redsun`, under the plugin id `positioner`.
Declare them and their links:

```yaml
presenters:
  positioner:
    plugin_name: redsun
    plugin_id: positioner
views:
  positioner_view:
    plugin_name: redsun
    plugin_id: positioner
    repeat_interval: 50
wiring:
  positioner_view.sig_move: positioner.move
  positioner_view.sig_move_to: positioner.move_to
  positioner_view.sig_stop: positioner.stop
  positioner_view.sig_configure: positioner.configure
  positioner.sig_readback: positioner_view.update_readback
  positioner.sig_moving: positioner_view.set_moving
  positioner.sig_failed: positioner_view.set_failed
  positioner.sig_configuration: positioner_view.update_configuration
```

The presenter takes every device with at least one axis. To show only some of
them, list them under `include`:

```yaml
presenters:
  positioner:
    plugin_name: redsun
    plugin_id: positioner
    include: [stage]
```

The view takes `repeat_delay`, the milliseconds a step button is held before
it repeats (400 by default); `repeat_interval`, the milliseconds between two
repeated steps (50 by default); and `steps`, the step sizes offered for each
axis (`0.001` to `1000` by decades).

## Declare it in Python

The same links, from `wire()`:

```{.python}
--8<-- "docs/examples/positioner.py:wire"
```

A plan that locks a device disables that device's controls while it runs.
The engine is not a session component, so this link is made in `wire()`, from
the presenter that holds the engine:

```{.python}
--8<-- "docs/examples/positioner.py:wire-locks"
```

## Use the view

- The Motors tab has a group per device and a row per axis. `-` and `+` step
  the axis by the size chosen beside them; held, they repeat. With the row
  focused, Left and Right do the same.
- "go to" sends the axis to the position typed, on Enter or with `Go`. When
  the device reports limits, a position outside them is refused.
- `Stop` appears for a device with an axis that can be stopped, and stops it.
- "moving" and "failed" show the state of each device; the tooltip of
  "failed" holds the error.
- `Save` keeps where a device stands, under a name you can edit, in the
  Saved positions section. `Go` on an entry moves that device back there.
- The Configuration tab shows each axis' configuration, such as `velocity`,
  and writes the entries that can be written.
- The Advanced tab sets the repeat interval, between 10 and 300 ms.

Saved positions and the repeat interval are kept in the session's
[`Settings`][redsun.Settings], one file per session on each machine.

## Show a setting a device does not declare

The Configuration tab shows what a device returns from
`describe_configuration()`. A signal the device does not declare as
configuration, such as the acceleration of an EPICS motor record, is not
shown. Declare it `StandardReadableFormat.CONFIG_SIGNAL` in a subclass of the
device to show it.

## Replace one half

The links above are the whole contract between the two components. A
presenter of your own with the same slots and signals works with the built-in
view, and a view of your own works with the built-in presenter.
[`PositionerGroup`][redsun.view.qt.builtins.PositionerGroup] is the group of
one device, ready to place in a view of your own.

## The example in full

??? example "The whole script"

    ```{.python}
    --8<-- "docs/examples/positioner.py"
    ```
