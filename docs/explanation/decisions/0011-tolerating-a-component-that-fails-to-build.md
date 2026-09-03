# 11. Tolerating a component that fails to build

Date: 2026-09-03

## Status

Accepted. Supersedes in part
[3. Structural subtyping for presenters and views](0003-structural-subtyping-for-presenters-and-views.md),
whose rule that a presenter or view failing to build re-raises and ends the
build no longer holds. What remains in force there is the dual gate: the
constructor's positional shape is checked at declaration, the protocol on the
built instance.

## Context

An application is a set of components, and a session runs against hardware that
is not always there. A device failing to build was already logged and skipped,
so that an unplugged instrument did not end the session. A presenter or view
failing to build re-raised, so that one panel refusing to construct left the
user with no window at all and a traceback in a terminal they may not have been
watching.

The asymmetry was not the only problem. Nothing downstream of the device phase
tolerated a component that was not there either:

| phase | reads components through | a component that failed |
|---|---|---|
| `_build_devices` | declarations | logged, skipped |
| `_build_presenters` | declarations | logged, re-raised |
| `_build_views` | declarations | logged, re-raised |
| `_register_providers` | `_instance_of` | `RuntimeError` |
| `_apply_wiring` | `_instance_of`, then `wire()` | `RuntimeError` |
| `_inject_dependencies` | `_instance_of` | `RuntimeError` |

`devices`, `presenters` and `views` read the same way, so the one path that was
meant to survive a failure did not: a container that logged "Failed to build
device 'bad'" and carried on raised `RuntimeError` on the next read of
`app.devices`.

## Decision

**A component that fails to build is recorded and skipped, whatever layer it
belongs to.** The build logs the failure at `ERROR` against the component's
name, keeps the exception under that name in `_failed`, and goes on to the next
component. `build` returns, and the application starts with the components it
has.

**Reading built components walks what was built, not what was declared.**
`_built_of` returns the instances a mapping of declarations produced, dropping
the entries with none. `devices`, `presenters` and `views` return that, and so
do the provider, wiring, injection and presenter-shutdown phases. The three
mappings can therefore be shorter than the declarations: `len(app.views)` is no
longer the number of `declare_view` calls.

**A `wire` body naming a component that failed does not end the wiring.**
Reading a `declare_*` attribute of a component that failed gives a stand-in
that answers any port with another stand-in, and `connect` returns `None`
without connecting when either end is one. The connections that name only
components that built are made. `connect` returns `Connection | None` as a
result, because a link that was not made has no `Connection` to report.

Only a component the build failed on resolves to a stand-in. Reading an
attribute of a component that built and naming a port it does not have still
raises, so a typo is still an error.

**A `wiring` rule naming a component that failed is skipped, not fatal.**
`VirtualContainer._resolve_port` raises `ComponentNotBuilt`, a `WiringError`
carrying the component name; `AppContainer._apply_wiring_config` catches it,
warns, and goes on to the next rule when the name is one the build failed on.
A rule naming a component that was never declared, one naming a port a built
component does not expose, a signature mismatch and a malformed rule all stay
fatal, because none of them is a component that failed.

**The build's closing line says what is missing.** It counts what was built
against what was declared, names the components that failed, and is logged at
`WARNING` rather than `INFO` when there are any:

```
Container built: 3/4 devices, 2/2 presenters, 4/5 views
Not built: bad_camera (device), log_panel (view)
```

## Consequences

- A session starts with an instrument unplugged or a panel refusing to
  construct, and the log says which part is missing.
- A `wire` body written before this change keeps working: every connection it
  declares is still attempted, and only the ones touching a component that
  failed are dropped.
- `AppContainer.connect` returns `Connection | None`. A caller reading the
  returned link has to narrow it.
- The exceptions are kept by name but are not public. A `failures` property is
  additive and can be added when something needs to read them.
- A view raising part-way through its own construction leaves behind whatever
  widgets it had already created. The container never receives a reference to
  them and cannot destroy them; a view parents its widgets at construction so
  that an early return leaves them owned.
