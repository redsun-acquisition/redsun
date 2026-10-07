---
icon: lucide/search
---

# How to find out why a component is missing

When the session can't build, set up or connect a
[component](../explanation/glossary.md#component), it logs the failure, leaves
the component out and opens the window without it. You can find the reason in
the log, or make the session stop on it instead.
[Sessions](../explanation/session.md#failed-components) explains why a session
carries on without the component.

## Prerequisites

You need a session that builds but lacks something, such as a view with no
dock, a button that does nothing, or a device missing from `app.devices`.

## Look at the window

In a Qt session, a view that failed to build and asked for a dock or the
centre is replaced there by a message that names the view and the reason, with
a **Show traceback** button. When any component failed to build or to be set
up, a button at the right of the status bar counts them, such as
`2 components failed`. Pressing it lists each one with its reason, and the
tracebacks are under **Show Details**.

## Read the build summary

The last line of the build counts what was made against what you declared.
When something is missing, the session logs it at `WARNING`, with a line for
each kind of failure:

```text
[29-09-26|08:42:44][WARNING]: Session built: 1/3 devices, 1/3 presenters, 0/0 views
Not built: odd (presenter), broken (device), remote (device, not connected), helper (presenter)
Not set up: ctrl (presenter)
```

- `Not built` lists the components left out. `not connected` marks a device
  that was made but did not connect within ten seconds.
- `Not set up` lists components that were built, and counted as built, but
  whose `setup` raised or asked for a component that was declared and not
  built. They are in the session and may not work.
- `Unused` lists services no built device names, when there are any.

A summary with no second line, logged at `INFO`, means nothing is missing.

The samples on this page leave out the end of each `WARNING` and `ERROR`
line, which names the file and line it was logged from.

## Find the reason

Each name in the summary has its own record earlier in the log, with the
reason after the colon, so search the log for the name:

- `Failed to build device 'broken': serial port COM3 not found`: the
  device's constructor raised.
- `Failed to connect device 'remote': ...`: the device did not connect.
- `Failed to build presenter 'helper': no calibration file`: the constructor
  raised, or the session refused the declaration before making anything.
- `Failed to set up presenter 'ctrl': 'helper' was not built`: its `setup`
  could not run.
- `Failed to start service 'stage_ioc': ...`: the service did not start.

A component without the members of its layer, such as a presenter whose
constructor takes `name` and never stores it, is refused before it is built and
reported the same way:

```text
Failed to build presenter 'odd': 'odd' is declared as a presenter, but does not satisfy 'NamedComponent': 'name' is missing
```

## Follow a failure back to its cause

A failure often causes others after it, so read the records from the first one
down:

```text
[29-09-26|08:42:57][ERROR]: Failed to start service 'stage_ioc': exited with code 1 before it was ready
[29-09-26|08:42:57][WARNING]: Services started: 0/1
Not started: stage_ioc (exited with code 1 before it was ready)
[29-09-26|08:42:57][ERROR]: Failed to build device 'stage': service 'stage_ioc' was not started
```

Here the device is missing because its service is. A service that exits
before it's ready also logs its last lines of output just above, starting with
`Service 'stage_ioc' exited with code 1 before it was ready; last output:`. The
service's own records are in its log file.

If a device names a service that answers too slowly, the report names the
service:

```text
Failed to connect device 'camera': service 'beamline' (attached) did not answer within 10 s: ...
```

The session skips a link that names a missing component and logs a warning, so
a line like this often explains a button that does nothing:

```text
Not connecting stage.readback: component 'stage' was not built
```

A link from the `wiring` section of a session file is logged with both ends,
as in `Not connecting stage.readback -> panel.on_position: component 'stage'
was not built`.

## When the build stops instead

A constructor or a `setup` that asks for a value nothing in the session
declares is a mistake in the session, not a component that failed. The build
logs the reason, gives back what it had started and raises a `TypeError`, and
it logs no summary:

```text
[29-09-26|08:42:44][ERROR]: Build stopped: 'ctrl.setup' asks for 'cal' (Calibration), which nothing in the session provides. ...
```

To fix it, declare the component or provider that shares the value, or give
the parameter `| None` and a default of `None`, as
[Make it optional](share-a-value.md#make-it-optional) shows.

## Open the log file

Each run also writes its records to a file, and
[Log files](../reference/log-files.md) says where it is.

To read the records in the window instead, add
[`LogView`][redsun.view.qt.builtins.LogView] to the session, as
[Show the logs in the application](configure-logging.md#show-the-logs-in-the-application)
shows. It holds the records of the build too.

## Make the session stop instead

Make the session [strict](../explanation/glossary.md#strict-session), in its
session file:

```yaml
strict: true
```

or for one run:

```python
MyApp({"strict": True}).run()
```

A strict session logs the same records and shuts down what it had started.
Then it raises [`BuildError`][redsun.BuildError], which lists each missing
component and its reason:

```text
redsun.errors.BuildError: A strict session is missing components:
  broken: serial port COM3 not found
  remote: position: NotConnectedError: ca://NOPE:Position
  helper: no calibration file
  odd: 'odd' is declared as a presenter, but does not satisfy 'NamedComponent': 'name' is missing
  ctrl: 'helper' was not built
```

In a test, build a `MyHeadlessApp` strict and mocked. It's a plain
[`Session`][redsun.Session] subclass with the declarations of `MyApp`, as
[How to write a component](write-a-component.md#test-it) shows, and it fails
with that list when a component is missing:

```python
def test_every_component_builds() -> None:
    MyHeadlessApp({"strict": True, "mock": True}).build().shutdown()
```
