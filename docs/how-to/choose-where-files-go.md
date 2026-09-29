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

A device that writes its own files and asks an `ophyd-async` `PathProvider`
where to put them, as the file-writing detectors of `ophyd-async` do. `redsun`
writes no acquisition data: the device, or the service behind it, chooses the
format and writes the bytes.

## Take the path provider

Name a constructor parameter `path_provider`:

```python
from ophyd_async.core import PathProvider, StandardReadable


class MyCamera(StandardReadable):
    def __init__(self, path_provider: PathProvider, name: str = "") -> None:
        self.path_provider = path_provider
        super().__init__(name=name)
```

The session passes its
[`SessionPathProvider`][redsun.path_provider.SessionPathProvider] to every
device with that parameter, by keyword, so it may not be positional-only. A
declaration or session file giving `path_provider` itself is refused. A device
without the parameter chooses its own paths.

Each file then goes to

```text
<base_dir>/<session>/<YYYY-MM-DD>/<datakey>/<plan>_<counter>
```

and the folder is created when the device asks for the path.

## Choose the folder

Set `base_dir` in the `storage` section of the session file:

```yaml
session: my-lab
storage:
  base_dir: "D:/experiments/2026-09"
```

In a session class, put it in `config`:

```python
class MyApp(QtSession):
    config: ClassVar[dict[str, Any]] = {
        "session": "my-lab",
        "storage": {"base_dir": "~/experiments"},
    }
```

`~` is expanded. Without `base_dir`, the root is the `redsun` folder in the
user data folder of the platform.

The `<session>` folder is the `session` name, or the name of the session class
when none is given. Each run of characters other than letters, digits, `.`,
`-` and `_` becomes `_`, so `my lab/run` writes into `my_lab_run`.

## Name the files after the plan

Link the signals of the component running plans to
[`set_plan`][redsun.path_provider.SessionPathProvider.set_plan] and
[`reset_plan`][redsun.path_provider.SessionPathProvider.reset_plan]:

```python
class MyApp(QtSession):
    ctrl: AsPresenter[MyController]
    camera: AsDevice[MyCamera]

    def wire(self) -> Iterator[Link]:
        yield self.ctrl.sig_started, self.path_provider.set_plan
        yield self.ctrl.sig_finished, self.path_provider.reset_plan
```

`sig_started` carries the plan's name. In a session file the provider is the
component `path_provider`:

```yaml
wiring:
  ctrl.sig_started: path_provider.set_plan
  ctrl.sig_finished: path_provider.reset_plan
```

Without these links, every file is named `unknown_<counter>`.

The counter is zero-padded to five digits; `storage.max_digits` changes the
width. It counts per plan and data key, continues from the highest number
already on disk, and does not start again on a new day. `reset_plan` reads the
disk again, so a name a device asked for and never wrote is given out again.

## Let the user change the folder

Link a signal carrying the new folder to
[`set_base_dir`][redsun.path_provider.SessionPathProvider.set_base_dir]:

```python
def wire(self) -> Iterator[Link]:
    yield self.folder_view.sig_directory_chosen, self.path_provider.set_base_dir
```

The next path is under the new folder, and the session's log files move there
too. `set_base_dir` raises `RuntimeError` between `set_plan` and `reset_plan`,
and in a session keeping a [catalog](keep-a-catalog.md), which fixes the folder
when it starts.

## Find the folder from code

A component reads the provider by asking for it by type:

```python
from redsun.path_provider import SessionPathProvider


class MyController:
    def __init__(self, name: str, *, paths: SessionPathProvider) -> None:
        self.name = name
        self.paths = paths
```

`paths.session_dir` is `<base_dir>/<session>`. Outside a session,
[`session_directory`][redsun.path_provider.session_directory] gives the same
folder under the default root:

```python
from redsun.path_provider import session_directory

session_directory("my-lab")
```
