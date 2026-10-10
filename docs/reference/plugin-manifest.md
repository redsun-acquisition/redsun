---
icon: lucide/plug
---

# Plugin manifest

Every key a [manifest](../explanation/glossary.md#manifest) can hold.
[How plugins provide components](../explanation/plugins.md) explains what a
plugin is and how a session finds one.

The file is YAML, inside the package of the plugin. Its schema is published
as [`plugin-manifest.schema.json`](schemas/plugin-manifest.schema.json).

## Keys

Every key is optional. A key that is not in this table is refused.

| Key | Type | Default | Holds |
| --- | --- | --- | --- |
| `name` | text | none | the name of the entry point; a manifest whose `name` differs from it is left out |
| `schema_version` | number | none | the version of the format of the manifest |
| `devices` | mapping | empty | device classes, by id |
| `presenters` | mapping | empty | presenter classes, by id |
| `views` | mapping | empty | view classes, by id |
| `providers` | mapping | empty | classes that share values with the components, by id |
| `services` | mapping | empty | [services](#services) a session can launch, by id |
| `hooks` | mapping | empty | hook provider classes, by the short name a session file gives them; only `redsun`'s own manifest is read |

A class is written `module:ClassName`.

```yaml
devices:
  stage: "my_plugin.devices:MyStage"

presenters:
  motor: "my_plugin.presenters:MotorPresenter"

views:
  motor-view: "my_plugin.views:MotorView"
```

## Services

An entry of `services`:

| Key | Type | Default | Holds |
| --- | --- | --- | --- |
| `module` | text | required | the module run as `python -m <module>` |
| `args` | list of text, or mapping | empty | the arguments after the module; a mapping is read as in the [session file](session-file.md) |
| `ready` | text | none | the line the service prints once it serves |
| `stop_timeout` | number | `10.0` | seconds each step of stopping waits |

A session file may give any of the four for the same service, and what it
gives replaces what the manifest says.

```yaml
services:
  stage-ioc:
    module: my_plugin.iocs.stage
    ready: "Server startup complete."
```

## Entry point

A package registers its manifest in the group `redsun.plugins`. The name of
the entry point is the `plugin_name` a session file uses, and its value is the
path of the manifest within the package.

```toml
[project.entry-points."redsun.plugins"]
my-plugin = "redsun.yaml"
```
