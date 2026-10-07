---
icon: lucide/folder-tree
---

# How to choose where acquisition files go

Give a device the session's
[path provider](../explanation/glossary.md#path-provider), choose the folder
the session writes under, and name the files after the plan that made them.
[Where a device writes](../explanation/components.md#where-a-device-writes)
explains the layout.

## Prerequisites

You need a device that writes its own files and asks an `ophyd-async`
`PathProvider` where to put them, as the file-writing detectors of `ophyd-async`
do. The blocks below are parts of one script, and the whole script is at the
end.

## Take the path provider

Name a constructor parameter `path_provider`:

```{.python}
--8<-- "docs/examples/acquisition_files.py:device"
```

The session passes its
[`SessionPathProvider`][redsun.path_provider.SessionPathProvider] to every
device with that parameter, by keyword, so a device that takes it by position
only is left out. You can't give `path_provider` yourself in a declaration or a
session file, because the session refuses it. A device without the parameter
chooses its own paths.

Each file then goes to

```text
<base_dir>/<session>/<YYYY-MM-DD>/<datakey>/<plan>_<counter>
```

and the folder is created when the device asks for the path. The session
also writes its log files under `<base_dir>/logs/<session>`.

## Choose the folder

Set `base_dir` in the `storage` section of the session file:

```yaml
session: my-lab
storage:
  base_dir: "D:/experiments/2026-09"
```

In a session class, put it in `config`:

```{.python}
--8<-- "docs/examples/acquisition_files.py:config"
```

Give an absolute folder, or one starting with `~`, which the session expands.
It accepts a relative folder here and refuses it only when a device asks for
its first path. Without `base_dir`, the root is the `redsun` folder in your
platform's user data folder.

The `<session>` folder is the `session` name, or the name of the session class
when you give none. Each run of characters other than letters, digits, `.`, `-`
and `_` becomes `_`, so `my lab/run` writes into `my_lab_run`.

## Name the files after the plan

Give the component that runs plans two signals: one it emits with the plan's
name when a plan starts, and one it emits when the plan ends:

```{.python}
--8<-- "docs/examples/acquisition_files.py:controller"
```

In `wire`, link them to
[`set_plan`][redsun.path_provider.SessionPathProvider.set_plan] and
[`reset_plan`][redsun.path_provider.SessionPathProvider.reset_plan]:

```{.python}
--8<-- "docs/examples/acquisition_files.py:wire-plan"
```

In a session file the provider is the component `path_provider`:

```yaml
wiring:
  ctrl.sig_started: path_provider.set_plan
  ctrl.sig_finished: path_provider.reset_plan
```

Without these links, every file is named `unknown_<counter>`.

To change the width of the counter, five digits by default, set
`storage.max_digits`.
[`SessionPathProvider`][redsun.path_provider.SessionPathProvider] describes
how the counter is kept.

## Let the user change the folder

Give a view a signal carrying the folder the user chose:

```{.python}
--8<-- "docs/examples/acquisition_files.py:view"
```

In `wire`, link it to
[`set_base_dir`][redsun.path_provider.SessionPathProvider.set_base_dir]:

```{.python}
--8<-- "docs/examples/acquisition_files.py:wire-folder"
```

The next path is under the new folder, and the session's log files move there
too. `set_base_dir` raises `RuntimeError` between `set_plan` and `reset_plan`.
It also raises it in a session that keeps a [catalog](keep-a-catalog.md),
because the catalog fixes the folder when it starts.

## Find the folder from code

A component gets the provider by asking for it by type, as `MyController`
above does with `paths: SessionPathProvider`, and `paths.session_dir` is
`<base_dir>/<session>`. Outside a session,
[`session_directory`][redsun.path_provider.session_directory] gives the same
folder under the default root:

```python
from redsun.path_provider import session_directory

session_directory("my-lab")
```

## The example in full

??? example "The whole script"

    ```{.python}
    --8<-- "docs/examples/acquisition_files.py"
    ```
