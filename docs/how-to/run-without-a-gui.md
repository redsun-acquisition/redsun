---
icon: lucide/terminal
---

# How to run a session without a GUI

A session built on [`Session`][redsun.Session] rather than
`redsun.qt.QtSession` shows nothing. This is what a headless deployment, or a
test, wants: every device, presenter and service comes up, and nothing asks
for a display.

## Install with no extra

`Session` needs no Qt package, so a plain install is enough:

```bash
pip install redsun
```

`redsun[pyqt]` and `redsun[pyside]` only exist to bring in a
[Qt binding](../explanation/glossary.md#qt-binding) for `QtSession`.

## Write the session

Subclass `Session` instead of `QtSession`:

```python
from redsun import AsDevice, AsPresenter, Session


class MyApp(Session):
    stage: AsDevice[MyMotor]
    stage_ctrl: AsPresenter[MyController]
```

No `views:` section, and no `AsView` declaration: a view is for showing
something, and there is nothing here to show it on.

## Build, use, shut down

```python
app = MyApp().build()
# app.stage_ctrl, app.stage and every other component are ready to use
app.shutdown()
```

`build` makes every component and every link, a coroutine slot included;
`shutdown` releases them. There is no `run`:
that method exists only on a session with a frontend, since it also shows a
window and starts that frontend's event loop.

Without an event loop, a signal sent to a slot that runs on the main thread,
as every slot of a view does, waits in a queue. Deliver what waits by calling
`psygnal.emit_queued()` on the main thread, for example in a test after the
action that sends the signal.

## Load one from a session file

A session file that names no `frontend` builds on the class
[`from_config`][redsun.Session.from_config] is called on:

```yaml
# session.yaml
session: my-lab

devices:
  stage:
    plugin_name: mylab
    plugin_id: my_motor

presenters:
  stage_ctrl:
    plugin_name: mylab
    plugin_id: my_controller
```

```python
from redsun import Session

app = Session.from_config("session.yaml").build()
```

When several files are layered, leave `frontend` out of every one of them;
naming it in one and not another disagrees about what kind of session this
is, which [Sessions](../explanation/session.md#the-configuration) says is not
allowed.

## Naming a frontend without its packages

A session file naming `frontend: qt` builds on `redsun.qt.QtSession`, so it
needs a Qt binding installed. Without one:

```text
ImportError: the configuration names frontend 'qt', which cannot be imported:
No module named 'app_model'. Install the packages it needs; the 'qt' frontend
comes with the 'pyqt' and the 'pyside' extra.
```

Install `redsun[pyqt]` or `redsun[pyside]`, or drop `frontend` from the file.
