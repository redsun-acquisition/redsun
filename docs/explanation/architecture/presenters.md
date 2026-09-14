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
synchronously on the engine's event loop thread and cannot await. To store a
derived result, such as a median image computed from Event documents, a
callback uses the storage layer's synchronous side: it calls `register` with a
[`StreamSpec`][redsun.storage.StreamSpec] built from the descriptor document,
then `put_nowait` on a [`FrameSink`][redsun.storage.FrameSink]. The design is
described in [Session storage](../storage.md) and
[ADR 0002](../decisions/0002-storage-dual-context-redesign.md).

## Built-in presenters

`redsun.presenter.builtins` holds presenters any session can use, declared in
Python or from a configuration file through the `redsun` plugin (see
[component system](../component-system.md#built-in-components)).

### `StoragePresenter`

[`StoragePresenter`][redsun.presenter.builtins.StoragePresenter] controls
where a session stores its data. It owns the
[`SessionPathProvider`][redsun.storage.SessionPathProvider], created with the
session name from the configuration, and registers it in the virtual container
under [`PATH_PROVIDER`][redsun.storage.PATH_PROVIDER]. Views follow the
provider through its `signals` (base directory and plan name).

The application connects two slots to the plan lifecycle:

```python
def wire(self) -> None:
    self.connect(self.acquisition.sig_pre_launch_notify, self.storage.set_plan)
    self.connect(self.acquisition.sig_plan_done, self.storage.reset_plan)
```

`set_plan` names burst files after the upcoming run; `reset_plan` sets the name
back to `unknown`, so bursts after a run are not filed under it. Only the
application knows which signals mean "a plan started", so nothing is connected
until it says so.

```yaml
presenters:
  storage:
    plugin_name: redsun
    plugin_id: storage
    base_dir: "~/my-data"   # optional; defaults to ~/redsun-storage
```

Its Qt view ships beside it:
[`StorageView`][redsun.view.qt.builtins.StorageView] shows the base directory
and lets the user change it. It resolves the same key, so an application
declaring the view without the presenter still builds and shows a read-only
placeholder.

```yaml
views:
  storage:
    plugin_name: redsun
    plugin_id: storage
```

[plans]: https://blueskyproject.io/bluesky/main/plans.html
[documents]: https://blueskyproject.io/bluesky/main/documents.html
