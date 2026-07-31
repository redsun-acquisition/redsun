# Presenters

`Presenters` represent the execution logic of your system.

Where `Devices` are "workers" (as they instruct your device to perform a certain task), `Presenters` **can be** "orchestrators", in the sense that they define the sequence of actions that workers must perform through Bluesky [plans].

We highlight "**can be**" because `Presenters` are not limited to that:

- they can consume Bluesky [documents] for on-the-fly processing, intermediate storage or redirection to a GUI (i.e. computing the FFT of an image and sending it to the GUI for display);
- they can provide manual control for device task execution and/or configuration;
  - in comparison to plans (which represents an experimental procedure), one may wish to - for example - manually move a motor stage from the GUI, or change the exposure time of a camera; the `Presenter` in this case acts as a middle-man between the GUI and the device, directly calling Bluesky methods and bypassing the `RunEngine`;
- they can act as communication points with external applications to trigger actions via a custom communication protocol (or wait for possible commands incoming by said applications).

`Presenters` are meant to communicate between each other via the [`VirtualContainer`][redsun.virtual.VirtualContainer], which takes care of redirecting information (commands and/or documents) to the appropriate destination (whether it is another `Presenter` or a `View`).

## The presenter contract

A presenter is recognized **structurally** through the
[`PPresenter`][redsun.presenter.PPresenter] protocol: any class whose
*instances* expose a `name` (`str`) and a `devices`
(`Mapping[str, Device]`) satisfies it. The protocol declares both members
as **read-only properties**, so implementers are free to use plain instance
attributes, class attributes, or properties - and `devices` may be any
`Mapping` subtype, such as a plain `dict`.

Compliance is a **dual gate**. At class level, the constructor's
positional shape is verified: its leading positional parameters must be
exactly `(name, devices)` - the container instantiates presenters as
`cls(name, devices, **config_kwargs)` and has no control over the keyword
arguments. At build time, the constructed instance is checked against the
protocol, raising a `TypeError` naming the missing members - attributes
assigned in `__init__` are invisible before instantiation
(see [ADR 0003](../decisions/0003-structural-subtyping-for-presenters-and-views.md)).

The [`Presenter`][redsun.presenter.Presenter] ABC is an optional
convenience base providing the conventional constructor shape:

- a `name`, used as the unique identifier of the presenter;
- a `Mapping[str, Device]` of the allocated devices in the session;
- additional keyword arguments, parsed from the session configuration file.

The ABC deliberately does *not* inherit the protocol - it satisfies it
structurally, like every other implementer.

Access to the virtual container is opt-in via the
[`IsProvider`][redsun.virtual.IsProvider] and
[`IsInjectable`][redsun.virtual.IsInjectable] protocols; synchronous
teardown via [`HasShutdown`][redsun.virtual.HasShutdown].

## Consuming documents

Presenters that process acquisition data subscribe to the `RunEngine`'s
document stream (directly, or through the callback registry on the
[`VirtualContainer`][redsun.virtual.VirtualContainer]). Document callbacks
run *synchronously* on the engine's event loop thread - they can never
await. To persist derived results (e.g. a median image computed from Event
documents), a callback uses the storage layer's synchronous face:
`register` a [`StreamSpec`][redsun.storage.StreamSpec] derived from the
descriptor document, then `put_nowait` on a
[`FrameSink`][redsun.storage.FrameSink]. The dual-context design is
documented in [Session storage](../storage.md) and
[ADR 0002](../decisions/0002-storage-dual-context-redesign.md).

## Built-in presenters

Reusable presenters ship in `redsun.presenter.builtins` and are available
both for declarative containers and from configuration files via the
`redsun` plugin (see [component system](../component-system.md#built-in-components)).

### `StoragePresenter`

[`StoragePresenter`][redsun.presenter.builtins.StoragePresenter] is the
application-level control point for storage paths. It owns the
[`SessionPathProvider`][redsun.storage.SessionPathProvider] (created with
the session name from the configuration), exposes it on the virtual
container as the `path_provider` DI provider, and wires plan lifecycle
signals: `sig_pre_launch_notify` sets the active plan name (so burst
filenames adopt it) and `sig_plan_done` resets it. Views observe the
provider through its `signals` (base directory and plan name).

```yaml
presenters:
  storage:
    plugin_name: redsun
    plugin_id: storage
    base_dir: "~/my-data"   # optional; defaults to ~/redsun-storage
```

[plans]: https://blueskyproject.io/bluesky/main/plans.html
[documents]: https://blueskyproject.io/bluesky/main/documents.html
