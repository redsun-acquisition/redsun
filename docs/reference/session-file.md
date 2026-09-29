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
| `providers` | mapping | empty | classes that share values with the components, by name |
| `storage` | mapping | the defaults below | [where files go](#storage), and the catalog |
| `wiring` | mapping | empty | [which signal reaches which slot](#wiring) |
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
| `args` | list of text | empty | the arguments after the module |
| `ready` | text | none | the line the service prints once it serves |
| `stop_timeout` | number | `10.0` | seconds each step of stopping waits |

```yaml
services:
  transport: pv-access
  camera_ioc:
    plugin_name: mylab
    plugin_id: camera-ioc
    prefix: "CAM:"
  beamline:
    prefix: "BL01:"
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

## Hooks

`hooks` maps a hook point to an entry.

| Key | Type | Default | Holds |
| --- | --- | --- | --- |
| `provider` | text | required | the class of the provider, as `module:ClassName` |
| `kwargs` | mapping | empty | the arguments the provider is made with |
