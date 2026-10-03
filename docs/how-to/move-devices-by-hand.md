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

Each axis is shown under its attribute name, or under its dotted path, such
as `left.x`, when two axes of one device share a name. This stage has two
axes, `x` and `y`:

```{.python}
--8<-- "docs/examples/positioner.py:device"
```

Axes are found by what they can do, never by their names, so the view makes
no assumption about which axis is which. [`find_axes`][redsun.utils.devices.find_axes]
returns what the positioner finds for a device.

The positioner describes and follows every axis when it is built. An axis
whose position is not a number, whose configuration cannot be read, or that
does not answer within `timeout` seconds (10 by default) is left out with a
warning, and the other axes are kept.

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
  positioner.sig_limits: positioner_view.update_limits
  positioner.sig_configuration: positioner_view.update_configuration
```

The presenter takes every device with at least one axis. To show only some of
them, list them under `include`; a name that is not a device of the session
is reported with a warning:

```yaml
presenters:
  positioner:
    plugin_name: redsun
    plugin_id: positioner
    include: [stage]
```

The view takes `repeat_delay`, the milliseconds a step button is held before
it repeats (400 by default); `repeat_interval`, the milliseconds between two
repeated steps (50 by default); `steps`, the step sizes offered for each
axis (`0.001` to `1000` by decades); `step_box`, `combobox` (the default) to
list those sizes or `spinbox` to take any size from the smallest to the
largest, its arrows moving it by decades; and `undo_delay`, the milliseconds
Undo is offered after a saved position is removed (5000 by default). Once a repeat
interval is set in the Advanced tab, it replaces `repeat_interval` in later
sessions.

A session holds one positioner presenter: the view asks for it in `setup`,
and two would leave the view with two answers, so it would not be built. Use
`include` on the one presenter to choose its devices.

## Declare it in Python

The same links, from `wire()`:

```{.python}
--8<-- "docs/examples/positioner.py:wire"
```

A plan that locks a device disables that device's controls while it runs,
`Stop` and its configuration included, and the presenter refuses moves and
configuration writes for it, a go-to already waiting included. To stop the
device, stop the plan: the engine stops every device the plan moved. The
engine is not a session component, so these links are made in `wire()`, from
the presenter that holds the engine:

```{.python}
--8<-- "docs/examples/positioner.py:wire-locks"
```

## Use the view

![The positioner view of the example session: a group for the stage, with a
row for each of its axes x and y](images/positioner.png)

- The Motors tab has a group per device and a row per axis. `-` and `+` step
  the axis by the size chosen beside them; held, they repeat. With the row or
  a step button focused, Left and Right do the same. A step starts from the
  setpoint, so steps add up exactly, and from the readback after a stop or a
  failure.
- The field beside `Go` shows where the axis is until you type a target;
  Enter or `Go` sends the axis there. A target that is not a number, or that
  falls outside the limits the device reports, is not sent, and the group says
  why. The limits are read again after each configuration write and after
  a move that is refused or fails, so a changed offset moves them too. An
  axis that checks its own targets, as an `ophyd-async` `StandardMovable`
  does, also refuses a target outside its current limits when it moves.
- `Stop` appears for a device that can be stopped, and stops the device and
  each of its axes at once; one that fails to stop is reported without
  keeping the others from stopping.
- "moving" and "failed" show the state of each device, with the error after
  "failed".
- `Save` keeps where a device stands, under a name you can edit, in the
  Saved positions section. `Go` on an entry moves that device back there,
  passing the same checks as a typed target. A saved position also keeps the
  configuration values in the units of the axis' position, such as an
  offset; when one has changed since, the first `Go` names it and the second
  moves. `x` removes an entry, and `Undo` brings it back for a few seconds
  after.
- The Configuration tab shows each axis' configuration, such as `velocity`,
  and writes the entries that can be written. A value changed on the device
  by anything else is shown as it changes.
- The Advanced tab sets the repeat interval, between 10 and 300 ms.

Saved positions and the repeat interval are kept in the session's
[`Settings`][redsun.Settings], one file per session on each machine, under keys
named after the view: a view renamed in the session file starts with none.

## Show a setting a device does not declare

The Configuration tab shows what each axis returns from
`describe_configuration()`. A signal the axis does not declare as
configuration, such as the acceleration of an EPICS motor record, is not
shown. Declare it `StandardReadableFormat.CONFIG_SIGNAL` in a subclass of the
axis' class to show it.

## Customize the positioner

### Change what a move does

The presenter is a dataclass. Subclass it as one, with `eq=False` as the base
has, and `kw_only=True` so that your fields are keyword arguments like the
base's `devices` and `include`. Every target, of a step or a go-to, passes
[`check`][redsun.presenter.PositionerPresenter.check] before it is sent, so a
subclass refusing more targets overrides `check` and calls `super().check`
first:

```{.python}
--8<-- "docs/examples/positioner_custom.py:presenter"
```

The new field is set like any other constructor keyword:

```{.python}
--8<-- "docs/examples/positioner_custom.py:declare"
```

`check`, the slots `move`, `move_to`, `stop`, `configure` and `set_locked`,
and the properties `axes` and `configuration` are the ones to override,
calling `super()`. A slot you override is marked with [`slot`][redsun.slot]
again, or it can no longer be wired. Methods with a leading underscore may
change.

### Change the view

[`group_class`][redsun.view.qt.builtins.PositionerView.group_class] is the
widget built for each device, and
[`tabs`][redsun.view.qt.builtins.PositionerView.tabs] holds the Motors,
Configuration and Advanced tabs. A subclass can replace the first and add to
the second:

```{.python}
--8<-- "docs/examples/positioner_custom.py:view"
```

A subclass can also set its own `placement`, or override a slot such as
`set_failed`, marked with `slot` again.

### Replace one half

The links above, and the
[`DescribesAxes`][redsun.presenter.DescribesAxes] protocol the view asks for
in `setup`, are the whole contract between the two components. A presenter
of your own with the same slots, signals and the `axes` and `configuration`
properties works with the built-in view, and a view of your own works with the
built-in presenter.
[`PositionerGroup`][redsun.view.qt.builtins.PositionerGroup] is the group of
one device, ready to place in a view of your own, and the helpers of
[`redsun.utils.devices`][redsun.utils.devices] read the axes, limits and
configuration of any device.

??? example "The customized session in full"

    ```{.python}
    --8<-- "docs/examples/positioner_custom.py"
    ```

## The example in full

??? example "The whole script"

    ```{.python}
    --8<-- "docs/examples/positioner.py"
    ```
