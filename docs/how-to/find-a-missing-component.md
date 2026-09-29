---
icon: lucide/search
---

# How to find out why a component is missing

A [component](../explanation/glossary.md#component) that the session could
not build, set up or connect is logged and left out, and the window opens
without it. Find the reason in the log, or make the session stop on it.
[Sessions](../explanation/session.md#a-component-that-fails-to-build)
explains why a session carries on without it.

## Prerequisites

A session that builds but lacks something: a view with no dock, a button that
does nothing, a device missing from `app.devices`.

## Read the build summary

The last line of the build counts what was made against what was declared.
When something is missing it is logged at `WARNING`, with a line for each kind
of failure:

```text
[29-09-26|08:42:44][WARNING]: Container built: 1/3 devices, 1/3 presenters, 0/0 views
Not built: odd (presenter), broken (device), remote (device, not connected), helper (presenter)
Not set up: ctrl (presenter)
```

- `Not built` lists the components left out. `not connected` marks a device
  that was made but did not connect within ten seconds.
- `Not set up` lists components that were built, and counted as built, but
  whose `setup` raised or asked for a component that was declared and not
  built. They are in
  the session and may not work.
- `Unused` lists services no built device names, when there are any.

A summary with no second line, logged at `INFO`, means nothing is missing.

The samples on this page leave out the end of each `WARNING` and `ERROR`
line, which names the file and line it was logged from.

## Find the reason

Each name in the summary has its own record earlier in the log, with the
reason after the colon. Search for the name:

- `Failed to build device 'broken': serial port COM3 not found`: the
  device's constructor raised.
- `Failed to connect device 'remote': ...`: the device did not connect.
- `Failed to build presenter 'helper': no calibration file`: the constructor
  raised, or the session refused the declaration before making anything.
- `Failed to set up presenter 'ctrl': 'helper' was not built`: its `setup`
  could not run.
- `Failed to start service 'stage_ioc': ...`: the service did not start.

A component that does not have the members of its layer, such as a presenter
whose constructor takes `name` and never stores it, is refused before it is
built, and reported the same way:

```text
Failed to build presenter 'odd': 'odd' is declared as a presenter, but does not satisfy 'NamedComponent': 'name' is missing
```

## Follow a failure back to its cause

A failure often causes others after it. Read the records from the first one
down:

```text
[29-09-26|08:42:57][ERROR]: Failed to start service 'stage_ioc': exited with code 1 before it was ready
[29-09-26|08:42:57][WARNING]: Services started: 0/1
Not started: stage_ioc (exited with code 1 before it was ready)
[29-09-26|08:42:57][ERROR]: Failed to build device 'stage': service 'stage_ioc' was not started
```

Here the device is missing because its service is. A service that exits
before it is ready also logs its last lines of output just above, starting
with `Service 'stage_ioc' exited with code 1 before it was ready; last output:`.
The service's own records are in its log file.

A device naming a service that answers too slowly is reported with the
service:

```text
Failed to connect device 'camera': service 'beamline' (attached) did not answer within 10 s: ...
```

A link that names a missing component is skipped with a warning, so a button
that does nothing is often explained by a line such as:

```text
Not connecting stage.readback: component 'stage' was not built
```

A link from the `wiring` section of a session file is logged with both ends,
as `Not connecting stage.readback -> panel.on_position: component 'stage' was
not built`.

## When the build stops instead

A constructor or a `setup` asking for a value that nothing in the session
declares is a mistake in the session, not a component that failed. The build
logs the reason, gives back what it had started, and raises a `TypeError`; no
summary is logged:

```text
[29-09-26|08:42:44][ERROR]: Build stopped: 'ctrl.setup' asks for 'cal' (Calibration), which nothing in the session provides. ...
```

Declare the component or provider that shares the value, or give the
parameter `| None` and a default of `None`, as
[Make it optional](share-a-value.md#make-it-optional) shows.

## Open the log file

Each run also writes its records to a file.
[Log files](../reference/log-files.md)
says where it is.

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

A strict session logs the same records, shuts down what it had started, then
raises [`BuildError`][redsun.BuildError] listing each missing component and
its reason:

```text
redsun.errors.BuildError: A strict session is missing components:
  broken: serial port COM3 not found
  remote: position: NotConnectedError: ca://NOPE:Position
  helper: no calibration file
  odd: 'odd' is declared as a presenter, but does not satisfy 'NamedComponent': 'name' is missing
  ctrl: 'helper' was not built
```

In a test, build strict and mocked a `MyHeadlessApp`: a plain
[`Session`][redsun.Session] subclass with the declarations of `MyApp`, as
[How to write a component](write-a-component.md#test-it) does. It fails with
that list when a component is missing:

```python
def test_every_component_builds() -> None:
    MyHeadlessApp({"strict": True, "mock": True}).build().shutdown()
```
