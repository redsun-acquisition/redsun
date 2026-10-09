---
icon: lucide/file-code
---

# Session file

Every key a [session file](../explanation/glossary.md#session-file) can hold.
[How to write a session file](../how-to/write-a-session-file.md) shows how to
write one, split it over several files and read a failure.

The file is YAML. Its schema is published as
[`session-file.schema.json`](schemas/session-file.schema.json).

## Top-level keys

Every key is optional.

| Key | Type | Default | Holds |
| --- | --- | --- | --- |
| `schema_version` | number | `1.0` | the format of the file; `1.0` is the only one |
| `session` | text | the name of the session class | the name of the session |
| `frontend` | `qt` | the frontend of the session class | the registered frontend to build on |
| `strict` | true or false | `false` | whether a component that fails to build or to set up stops the session |
| `mock` | true or false | `false` | whether devices connect to simulated backends, and no service is launched |
| `metadata` | mapping | empty | anything to record with the session |
| `services` | mapping | empty | the [services](#services) devices talk to |
| `devices` | mapping | empty | the [devices](#components), by name |
| `presenters` | mapping | empty | the [presenters](#components), by name |
| `views` | mapping | empty | the [views](#components), by name |
| `layout` | mapping | the layout of the session class | [where the views start](#layout) in the window |
| `shortcuts` | mapping | empty | [keys](#shortcuts) replacing what the components declare |
| `providers` | mapping | empty | classes that share values with the components, by name |
| `storage` | mapping | the defaults below | [where files go](#storage), and the catalog |
| `wiring` | mapping | empty | [which signal reaches which slot](#wiring) |
| `pairs` | list | empty | [components linked to each other](#pairs), two names each |
| `hooks` | mapping | empty | the [hook providers](#hooks), by hook point |
| `actions` | | none | menu and toolbar commands of a Qt session |
| `color_scheme` | `system`, `light` or `dark` | `system` | the colour scheme a Qt session starts with |

A file given to `Session.from_config` must set `session`.

```yaml
schema_version: 1.0
session: my-lab
frontend: qt
strict: false
mock: false
metadata:
  user: Ada
  setup: iSCAT
color_scheme: dark
```

## Components

`devices`, `presenters` and `views` map the name of each component to its
entry.

| Key | Type | Default | Holds |
| --- | --- | --- | --- |
| `plugin_name` | text | none | the plugin whose manifest lists the class |
| `plugin_id` | text | none | the id of the class in that manifest |
| `service` | text | none | devices only: the service whose [prefix](../explanation/glossary.md#prefix) the device gets |
| `autoconnect` | true or false | `true` | devices only: whether the build connects the device |
| `placement` | text or mapping | the view's own | views only: where the view goes in the window, as a word or mapping the frontend reads; see [Override a view's default placement](../how-to/place-a-view.md#override-a-views-default-placement) |
| any other key | | | an argument of the constructor |

An entry for a component the session class declares leaves out `plugin_name`
and `plugin_id`.

```yaml
presenters:
  motor_ctrl:
    plugin_name: my-plugin
    plugin_id: motor
    step: 2.0
```

## Services

`services` maps the name of each service to its entry, and holds one key of
its own, `transport`.

| Key | Type | Default | Holds |
| --- | --- | --- | --- |
| `transport` | `channel-access` or `pv-access` | `channel-access` | the protocol every service of the session speaks |

An entry:

| Key | Type | Default | Holds |
| --- | --- | --- | --- |
| `plugin_name` | text | none | the plugin whose manifest lists the service |
| `plugin_id` | text | none | the id of the service in that manifest |
| `prefix` | text | none | the prefix given to each device naming the service |
| `module` | text | none | the module to run; an entry without one is attached to |
| `args` | list of text, or mapping | empty | the arguments after the module; a mapping gives `--key value` per option |
| `ready` | text | none | the line the service prints once it serves |
| `stop_timeout` | number | `10.0` | seconds each step of stopping waits |
| `address` | text | none | where an attached service answers, added to the address list of the transport |

A mapping under `args` becomes arguments this way:

| Value | Arguments |
| --- | --- |
| text or number | `--key value` |
| `true` | `--key` |
| `false` or `null` | none |
| list | `--key` followed by each item |

```yaml
services:
  transport: pv-access
  camera_ioc:
    plugin_name: mylab
    plugin_id: camera-ioc
    prefix: "CAM:"
    args:
      exposure: 0.1
      simulate: true
  beamline:
    prefix: "BL01:"
    address: 10.0.0.5
```

## Storage

| Key | Type | Default | Holds |
| --- | --- | --- | --- |
| `base_dir` | path | the user data folder | the root the session writes under |
| `max_digits` | whole number | `5` | the width of the counter in file names |
| `catalog` | mapping | none | the catalog of runs; absent, the session keeps none |
| `catalog.readable` | list of paths | empty | folders the catalog may read besides those of the session |

```yaml
storage:
  base_dir: "D:/experiments/2026-09"
  max_digits: 5
  catalog:
    readable: [/data/camera]
```

## Wiring

`wiring` maps a signal to a slot, or to a list of slots. Both are written
`component.port`.

```yaml
wiring:
  motor_ctrl.sig_moved: motor_widget.refresh
```

## Pairs

`pairs` lists two components by name. Each signal of one reaches each slot of
the other that names it in its `signal`, both ways. A pairing that connects
nothing is refused, and one naming a component that failed to build is skipped
with a warning.

```yaml
pairs:
  - [motor_ctrl, motor_widget]
```

## Layout

`layout` sets where the views start in the window. It replaces the layout the
session class returns from `window_layout()`, and a later file's `layout`
replaces an earlier one whole.

```yaml
layout:
  regions:
    center: {tabs: [image, plot]}
    left: {tabs: [stage, lights], current: stage}
    right: {column: [plans, {tabs: [progress, files]}], sizes: [1, 2]}
    bottom: log
  sizes: {left: 0.2, right: 0.3, bottom: 0.15}
  hidden: [log]
```

| Key | Type | Default | Holds |
| --- | --- | --- | --- |
| `regions` | mapping | empty | what fills each region of the window; the Qt frontend has `center`, `left`, `right`, `top` and `bottom` |
| `sizes` | mapping | empty | the share of the window each region takes, between 0 and 1: of its width for `left` and `right`, of its height for `top` and `bottom` |
| `hidden` | list | empty | the views that start hidden |

A region holds a view's name, or one of these mappings:

| Key | Type | Default | Holds |
| --- | --- | --- | --- |
| `row` | list | required | views side by side, left to right |
| `column` | list | required | views stacked, top to bottom |
| `sizes` | list | equal shares | with `row` or `column`: one positive weight per child |
| `tabs` | list | required | the names of views sharing one space as tabs |
| `current` | text | the first tab | with `tabs`: the view shown on top |

A view the layout leaves out goes where its placement asks. A name no view
answers to is logged and left out, and refused when `strict` is set.

## Shortcuts

`shortcuts` gives commands other keys than the components declare. A
command is named `<component>.<method>`, after the component's name in the
session and the method its shortcut runs.

```yaml
shortcuts:
  acquisition_view.run_selected: Ctrl+Shift+R
  acquisition.stop: [Ctrl+., Escape]
  positioner.step_back: null
```

| Key | Type | Default | Holds |
| --- | --- | --- | --- |
| `<component>.<method>` | text, a list of two, or `null` | the component's key | the key, two keys, or `null` for none |

A key is written as the frontend reads it; for Qt, `Ctrl` is the Command key
on macOS. A key two commands ask for in the same place stays with the first,
and the change is logged, or refused when `strict` is set.

## Hooks

`hooks` maps a hook point to an entry.

| Key | Type | Default | Holds |
| --- | --- | --- | --- |
| `provider` | text | required | the class of the provider, as `module:ClassName` |
| `kwargs` | mapping | empty | the arguments the provider is made with |
