---
icon: lucide/plug
---

# How to connect a device on demand

You don't have to connect a device when the session builds it. You can build
it unconnected and have a component connect it when the user asks.
[Connecting](../explanation/components.md#connecting) explains what the build
does with the other devices.

## Prerequisites

You need a session that declares the device, and a component that uses it.
The blocks below are parts of one script, and the whole script is at the end.

## Declare the device unconnected

Give the declaration
[`autoconnect=False`](../explanation/glossary.md#autoconnect):

```{.python}
--8<-- "docs/examples/connect_on_demand.py:declare"
```

`MyMotor` is in the whole script at the end. It names no service, so you give
its `prefix` here.

In a session file, write it like this:

```yaml
devices:
  motor:
    plugin_name: mylab
    plugin_id: motor
    autoconnect: false
```

The build creates the device and adds it to `devices`, but doesn't connect it.
[Session file](../reference/session-file.md#components) lists what
`autoconnect` accepts.

## Connect it from a component

Ask for the devices and connect in an `async` slot:

```{.python}
--8<-- "docs/examples/connect_on_demand.py:controller"
```

The controller reads `mock` from [`SessionConfig`][redsun.SessionConfig], so in
a [mocked session](../explanation/glossary.md#mocked-session) it connects
the device to a simulated backend, as the build does with the others.

## Ask for it from a view

Give the view a signal to ask with and slots for the answers:

```{.python}
--8<-- "docs/examples/connect_on_demand.py:view"
```

Link them in the session:

```{.python}
--8<-- "docs/examples/connect_on_demand.py:session"
```

## Shut it down unconnected

The session calls the device's `shutdown` when it ends, whether or not a
component connected the device.

!!! warning "`shutdown` can run on a device that never connected"

    A `shutdown` that writes to the hardware has to cope with a device that
    never connected. Make it check that the device connected first.

## The example in full

??? example "The whole script"

    ```{.python}
    --8<-- "docs/examples/connect_on_demand.py"
    ```
