---
icon: lucide/file-code
---

# How to write a session file

A [session file](../reference/glossary.md#session-file) is a YAML file with a
session's settings. This page lists every key it can hold.

## Let your editor check it

Put this line first, and an editor with a YAML language server checks the file
as you type:

```yaml
# yaml-language-server: $schema=https://redsun-acquisition.github.io/redsun/reference/schemas/session-file.schema.json
```

## The keys

```yaml
schema_version: 1.0     # the format of this file; 1.0 is the only one
session: my-lab         # the session's name
frontend: qt            # the registered frontend to build on
strict: false           # stop if a component fails to build
metadata:               # anything you want recorded with the session
  user: Ada
  setup: iSCAT

services: ...           # processes and servers devices talk to
devices: ...            # the device layer
presenters: ...         # the presenter layer
views: ...              # the view layer
providers: ...          # shared values from plugins
storage: ...            # where files go, and the catalog
wiring: ...             # which signal reaches which slot
hooks: ...              # objects acting on the toolkit
actions: ...            # menu and toolbar commands (Qt)
color_scheme: dark      # system, light or dark (Qt)
```

Every key is optional. Without `session`, a session is named after its class;
a file given to `Session.from_config` must set it. Without `frontend`, the
session builds on the class it was made from.

### Components

`devices`, `presenters` and `views` map each component's name to its
settings:

```yaml
presenters:
  motor_ctrl:
    plugin_name: my-plugin   # the plugin offering the class
    plugin_id: motor         # its id in that plugin's manifest
    step: 2.0                # every other key goes to the constructor
```

For a component the session class already declares, leave out `plugin_name`
and `plugin_id`: the entry only gives constructor arguments.

A device entry also takes `service`, the service whose prefix it gets, and
`autoconnect: false`, to leave it unconnected.

### Services

```yaml
services:
  transport: pv-access       # channel-access (the default) or pv-access
  camera_ioc:
    plugin_name: mylab
    plugin_id: camera-ioc
    prefix: "CAM:"
  beamline:
    prefix: "BL01:"          # no module: an attached service
```

A launched service entry may also give `module`, `args`, `ready` and
`stop_timeout`. See [Write a service](write-a-service.md).

### Storage

```yaml
storage:
  base_dir: "D:/experiments/2026-09"   # the session's root folder
  max_digits: 5                        # width of the file counter
  catalog:                             # keep a catalog of runs
    readable: [/data/camera]           # other folders it may read
```

See [Keep a catalog of runs](keep-a-catalog.md).

### Wiring

```yaml
wiring:
  - from: motor_ctrl.sig_moved
    to: motor_widget.refresh
```

See [Wire components together](wire-components.md).

### Hooks and actions

See [Install hooks](install-hooks.md) and [Add menu actions](add-menu-actions.md).

## Split a configuration over several files

A session class lists its sources in `config`. They are read in order, and a
later one wins:

```python
class Simulation(QtSession):
    config = ["common.yaml", "simulation.yaml"]
```

A subclass's sources come after its base class's. A source can also be a
mapping, which is handy for one setting:

```python
app = Simulation({"session": "morning-run"})
```

Two rules stop a later source from changing what kind of session this is:
`schema_version`, `frontend` and `services.transport` must be the same in every
source that sets them. And a component's entry is replaced whole: a later file
naming `motor_ctrl` gives all of its settings.

A file that only makes sense layered over another, such as one holding a
`presenters` section alone, is fine: only the merged result is checked.

## Read a failure

A mistake raises [`ConfigurationError`][redsun.ConfigurationError] before
anything is built, listing every problem:

```text
ConfigurationError: Configuration (session.yaml) is invalid:
  storage.max_digits: Input should be a valid integer, unable to parse string as an integer
  presentrs: Extra inputs are not permitted
```
