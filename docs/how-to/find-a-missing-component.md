---
icon: lucide/search
---

# How to find out why a component is missing

Sometimes a session opens, but something you declared isn't there: a view
has no dock, a button does nothing, or a device is missing from `app.devices`.
That happens when the session can't build, set up or connect a
[component](../explanation/glossary.md#component). Instead of stopping, it
logs what went wrong, leaves the component out, and opens the window without
it. [Sessions](../explanation/session.md#components-that-fail-to-build)
explains why it carries on.

This page shows where the session tells you what failed and why, how to trace
one failure back to the one that caused it, and how to make the session stop
on the first failure instead.

## Look at the window

In a Qt session, the window already tells you that something is missing:

- A view that failed to build, and that should have filled a dock or the
  centre of the window, is replaced there by a message naming the view and
  the reason. Its **Show traceback** button shows where the error came from.
- When any component failed to build or to be set up, a button at the right
  of the status bar counts them, such as `2 components failed`. Press it to
  see each one with its reason, and **Show Details** for the tracebacks.

## Read the build summary

The log gives the full picture. At the end of every build the session logs a
summary, which counts what it made against what you declared. When nothing is
missing, the summary is a single line at `INFO`. When something is missing, it
is logged at `WARNING`, with one more line for each kind of problem:

```text
[29-09-26|08:42:44][WARNING]: Session built: 1/3 devices, 1/3 presenters, 0/0 views
Not built: odd (presenter), broken (device), remote (device, not connected), helper (presenter)
Not set up: ctrl (presenter)
```

- `Not built` lists the components the session left out. A device marked
  `not connected` was made, but didn't connect within ten seconds.
- `Not set up` lists components that were built, and are counted as built,
  but whose `setup` raised or asked for a component that wasn't built. They
  are in the session, but they may not work.
- `Unused` lists services that no built device names. The line appears only
  when there are some.

The log goes to the console, and each run also writes it to a file;
[Log files](../reference/log-files.md) says where. To read it in the window
instead, add [`LogView`][redsun.view.qt.builtins.LogView] to the session, as
[Show the logs in the application](configure-logging.md#show-the-logs-in-the-application)
shows. It holds the records of the build too.

The examples on this page leave out the end of each `WARNING` and `ERROR`
line, which names the file and line of code it was logged from.

## Find the reason

Each name in the summary has a record of its own earlier in the log, which
starts with `Failed to` and gives the reason after the colon. Search the log
for the name, and you'll find one of these:

- `Failed to build device 'broken': serial port COM3 not found` means the
  device's constructor raised.
- `Failed to connect device 'remote': ...` means the device was made but
  didn't connect.
- `Failed to build presenter 'helper': no calibration file` means the
  constructor raised, or the session refused the declaration before making
  anything.
- `Failed to set up presenter 'ctrl': 'helper' was not built` means its
  `setup` couldn't run.
- `Failed to start service 'stage_ioc': ...` means the service didn't start.

The session also refuses a component that lacks what every component of its
layer must have, such as a presenter whose constructor takes `name` but never
stores it. It never builds it, and reports it the same way:

```text
Failed to build presenter 'odd': 'odd' is declared as a presenter, but does not satisfy 'NamedComponent': 'name' is missing
```

## Follow a failure back to its cause

One failure often causes others after it, so start from the first `Failed to`
record and read down. In this log, the device is missing because its service
is:

```text
[29-09-26|08:42:57][ERROR]: Failed to start service 'stage_ioc': exited with code 1 before it was ready
[29-09-26|08:42:57][WARNING]: Services started: 0/1
Not started: stage_ioc (exited with code 1 before it was ready)
[29-09-26|08:42:57][ERROR]: Failed to build device 'stage': service 'stage_ioc' was not started
```

A service that exits before it's ready also logs its last lines of output just
above these records, starting with
`Service 'stage_ioc' exited with code 1 before it was ready; last output:`.
For everything else it printed, open the service's own log file.

When a device's service answers too slowly, the record names the service, so
you know where to look:

```text
Failed to connect device 'camera': service 'beamline' (attached) did not answer within 10 s: ...
```

A button that does nothing is often a link the session skipped. When a link
names a component that wasn't built, the session leaves the link out and logs
a warning:

```text
Not connecting stage.readback: component 'stage' was not built
```

A link from the `wiring` section of a session file is logged with both ends,
as in `Not connecting stage.readback -> panel.on_position: component 'stage'
was not built`.

!!! warning "A value nothing provides stops the build"

    A constructor or a `setup` that asks for a value nothing in the session
    declares is a mistake in the session itself, not a component that failed.
    So the build doesn't carry on: it logs the reason, shuts down what it had
    started, and raises a `TypeError`, with no summary:

    ```text
    [29-09-26|08:42:44][ERROR]: Build stopped: 'ctrl.setup' asks for 'cal' (Calibration), which nothing in the session provides. ...
    ```

    To fix it, declare the component or provider that shares the value, or
    give the parameter `| None` and a default of `None`, as
    [Make it optional](share-a-value.md#make-it-optional) shows.

## Make the session stop instead

While you're putting a session together, you may prefer it to stop at the
first missing component rather than open without it. Make the session
[strict](../explanation/glossary.md#strict-session), in its session file:

```yaml
strict: true
```

or for one run:

```python
MyApp({"strict": True}).run()
```

A strict session logs the same records and shuts down what it had started.
Then it raises [`BuildError`][redsun.BuildError], which lists each missing
component with its reason:

```text
redsun.errors.BuildError: A strict session is missing components:
  broken: serial port COM3 not found
  remote: position: NotConnectedError: ca://NOPE:Position
  helper: no calibration file
  odd: 'odd' is declared as a presenter, but does not satisfy 'NamedComponent': 'name' is missing
  ctrl: 'helper' was not built
```

The same check makes a good test. Build a `MyHeadlessApp` strict and mocked,
and the test fails with that list whenever a component is missing.
`MyHeadlessApp` is a plain [`Session`][redsun.Session] subclass with the
declarations of `MyApp`, as
[How to write a component](write-a-component.md#test-it) shows:

```python
def test_every_component_builds() -> None:
    MyHeadlessApp({"strict": True, "mock": True}).build().shutdown()
```
