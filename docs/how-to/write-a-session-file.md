---
icon: lucide/file-code
---

# How to write a session file

Write a [session file](../explanation/glossary.md#session-file), a YAML file
with the settings of a session, have an editor check it, and split it over
several files.

## Let your editor check it

Put this line first, and an editor with a YAML language server checks the file
as you type:

```yaml
# yaml-language-server: $schema=https://redsun-acquisition.github.io/redsun/reference/schemas/session-file.schema.json
```

## Write the sections you need

Every key is optional, so a file holds only what differs from what the
session class declares. This one names the session, gives an argument to a
presenter the class declares, and moves the files of the session:

```yaml
session: my-lab

presenters:
  motor_ctrl:
    step: 2.0

storage:
  base_dir: "D:/experiments/2026-09"
```

[Session file](../reference/session-file.md) lists every key, with its type
and its default. For the sections that have a guide of their own:

- `services`: [Write a service](write-a-service.md)
- `storage.base_dir`, `storage.max_digits`:
  [Choose where acquisition files go](choose-where-files-go.md)
- `storage.catalog`: [Keep a catalog of runs](keep-a-catalog.md)
- `wiring`: [Wire components together](wire-components.md)
- `hooks`: [Install hooks](install-hooks.md)
- `actions`: [Add menu actions](add-menu-actions.md)

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

Layered files merge `wiring` by signal: a later file naming a new signal adds
it, and naming one already wired replaces its slots. `pairs` adds the
pairings of every file.

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
