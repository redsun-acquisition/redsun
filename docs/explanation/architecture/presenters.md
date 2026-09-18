# Presenters

A presenter holds the logic of a session.

Devices do the work on hardware. A presenter can decide the order of that work, through `bluesky` [plans], but it is not limited to that. A presenter can also:

- consume `bluesky` [documents] to process them on the fly, store intermediate results or forward them to the interface (for example, computing the FFT of an image and sending it to a view);
- control devices by hand: move a motor stage or change a camera's exposure from the interface, calling the device directly without going through the `RunEngine`;
- talk to external applications over a protocol of its own, sending commands or waiting for them.

Presenters talk to each other and to views through the [`VirtualContainer`][redsun.virtual.VirtualContainer], which routes commands and documents to whoever receives them.

## The presenter contract

A presenter is recognised by shape, through the
[`PPresenter`][redsun.presenter.PPresenter] protocol: any class whose
instances expose a `name` (`str`) and `devices` (`Mapping[str, Device]`)
satisfies it. The protocol declares both as read-only properties, so an
implementer may use instance attributes, class attributes or properties, and
`devices` may be any `Mapping`, such as a `dict`.

A presenter is checked twice. When the class is declared, its constructor's
leading positional parameters must be exactly `(name, devices)`: the container
calls `cls(name, devices, **config_kwargs)`. When it is built, the instance is
checked against the protocol, and a `TypeError` names the missing members.
Attributes assigned in `__init__` do not exist before the instance does, which
is why the second check runs on the instance
(see [ADR 0003](../decisions/0003-structural-subtyping-for-presenters-and-views.md)).

The [`Presenter`][redsun.presenter.Presenter] ABC is an optional base with the
usual constructor:

- a `name`, the presenter's unique identifier;
- a `Mapping[str, Device]` of the session's devices;
- keyword arguments from the session configuration file.

The ABC does not inherit the protocol; it satisfies it by shape, like any
other implementer.

A presenter reaches the virtual container by implementing
[`IsProvider`][redsun.virtual.IsProvider] or
[`IsInjectable`][redsun.virtual.IsInjectable], and is shut down through
[`HasShutdown`][redsun.virtual.HasShutdown].

## Consuming documents

A presenter processing acquisition data subscribes to the `RunEngine`'s
documents, directly or through the callback registry of the
[`VirtualContainer`][redsun.virtual.VirtualContainer]. Document callbacks run
synchronously on the engine's event loop thread and cannot await. A presenter
storing a derived result, such as a median image computed from Event documents,
reads the `StreamResource` document for the store the device wrote and adds its
product to it. The acquisition itself belongs to the device, as
[ADR 0013](../decisions/0013-acquisition-storage-belongs-to-the-device.md)
records.

## The session's path provider

The container builds one
[`SessionPathProvider`][redsun.path_provider.SessionPathProvider] per session
and hands it to every device taking a `path_provider` keyword, so every file a
session writes lands under one root:

```
<base_dir>/<session>/<YYYY-MM-DD>/<datakey>/<plan>_<counter>
```

The data key names the last directory, so each detector writes into one of its
own. Counters belong to `(plan, datakey)`, so two detectors in one run are both
`<plan>_00003`.

The root comes from the session file, and defaults to the user data directory,
beside the session's logs:

```yaml
session: my-session
storage:
  base_dir: "D:/experiments/2026-09"   # optional
  max_digits: 5                        # optional, width of the counter
```

The provider is published for wiring as `path_provider`, and a component
resolves it through
[`PATH_PROVIDER`][redsun.path_provider.PATH_PROVIDER]:

```python
provider = container.require(PATH_PROVIDER)
provider.base_dir  # where files go now
provider.set_base_dir("E:/other-disk")  # where they go from the next run on
```

A component named `path_provider` is refused, since it would shadow the
provider in the wiring.

### The plan lifecycle

Three slots, connected to whatever announces a run:

```yaml
wiring:
  - from: acquisition.sig_pre_launch_notify
    to: path_provider.set_plan
  - from: acquisition.sig_plan_done
    to: path_provider.reset_plan
  - from: output_dir_widget.sig_directory_chosen
    to: path_provider.set_base_dir
```

`set_plan` names files after the upcoming run and `reset_plan` sets the name
back to `unknown`, so files written after a run are not filed under it. Only
the application knows which signals mean "a plan started", so nothing is
connected until it says so.

`set_base_dir` raises `RuntimeError` while a plan is running, since the run's
remaining files would land somewhere else than the ones already written. A GUI
offering the root as an editable field catches it and says so. A session that
does not wire `set_plan` and `reset_plan` cannot tell that a plan is running,
so it does not raise.

### What is not supported

A device cannot be given a root of its own from configuration. `path_provider`
is reserved, as `service` and `autoconnect` are, and there is no per-device
`base_dir`. One root per session is what makes a session archivable as a unit
and what keeps a catalog's readable roots correct. A device that has to write
elsewhere, to a scratch disk or inside a container, does not take the keyword
and owns its paths:

```python
class FastCamera(Device):
    def __init__(self, name: str, scratch: str) -> None:
        super().__init__(name=name)
        self._provider = StaticPathProvider(UUIDFilenameProvider(), scratch)
```

Two devices must not share a data key. The key is the directory and the
counter, so both would write the same filenames into the same place, and the
writer that closes last is the one whose data survives.

A device's own provider cannot be retargeted from outside.
`ophyd-async`'s `PathProvider` is a protocol with one method, `__call__`, and
no interface for changing where it points. `set_base_dir` exists because
`redsun` built that provider itself. If `ophyd-async` grows a public
interface, this is what follows it.

[plans]: https://blueskyproject.io/bluesky/main/plans.html
[documents]: https://blueskyproject.io/bluesky/main/documents.html
