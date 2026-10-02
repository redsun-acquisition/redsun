# 20. A built-in positioner

Date: 2026-10-03

## Status

Accepted

## Context

Every session that moves a stage by hand needs a presenter that moves its
axes and a view to drive them. Each plugin wrote both for its own device
class, and the views took the names of the axes as given: an arrow pad for
`x` and `y`, a pair of buttons for `z`. A device with other axes, or other
names for them, needed another view.

Nothing about moving an axis by hand depends on the device. `ophyd-async`
already says what an axis can do: `set` moves it, `locate` reports where it
is, `subscribe` follows its readback, and a `Stoppable` one can be stopped.
Speed, acceleration and the like are the device's configuration, read with
`describe_configuration`.

## Decision

`redsun` ships `PositionerPresenter` and `PositionerView`, registered under
the plugin id `positioner`.

- An axis is found by protocol on a device and its descendants: it is
  `AsyncLocatable` and `Subscribable`, and not a `Signal`, since every
  writable signal can be set and located too. The search stops at the first
  axis on each branch. Axes are never chosen by name or by count.
- The view has one row per axis, grouped by device: readback, step buttons
  repeating while held, step size, go-to, and per device its state, a Stop
  button for stoppable axes, and saved positions kept in the session's
  settings.
- Limits come from the readback descriptor's `limits`, when a device reports
  them.
- The configuration of every axis is shown in a `DescriptorTreeView` and
  written through the presenter. A signal a device does not declare as
  configuration is not looked for by attribute name.
- The links between the two components are their whole interface, so either
  can be replaced. `find_axes` and `PositionerGroup` are public for
  components of your own.

## Consequences

- The names of both components, their signals and slots, `find_axes`,
  `Axis`, `AxisInfo`, `DescribesAxes` and `PositionerGroup` are public API.
- A device's own behaviour stays in the device: its `MovableLogic` decides
  the tolerance of a move, what stopping does and how long a move may take.
- A device shows a setting in the Configuration tab by declaring it
  `CONFIG_SIGNAL`.
- No velocity, acceleration or limit controls exist beyond what devices
  declare.
