---
icon: lucide/arrow-right-left
---

# How to migrate from 0.17

Release 0.18 changes how the `sharedbox` transport lays out its boxes, and
keeps the keyword `title` for the session. This page gives the changes your
code or your setup may need. The
[changelog](../reference/changelog.md) lists everything else the release
changed.

## A sharedbox service and its session upgrade together

The [`sharedbox` transport](serve-over-sharedbox.md) serves each attribute of
a `fastcs` controller as one field of its box, so a service and a session
must come from the same `redsun` release. A session of 0.18 that attaches to
a service still running 0.17, or the other way round, fails to connect the
device with `sharedbox.SchemaMismatchError`. Install the same release in the
environment of the service and in that of the session:

```bash
# 0.17: the service's and the session's environments may differ
uv add "redsun[sharedbox]==0.17.0"

# now: upgrade both
uv add "redsun[sharedbox]>=0.18"
```

The code of a device or a service needs no change:
[`BoxDeviceConnector`][redsun.device.sharedbox.BoxDeviceConnector] and
[`BoxTransport`][redsun.services.sharedbox.BoxTransport] take the same
arguments as before.

A device now raises
[`ServiceExitedError`][redsun.device.sharedbox.ServiceExitedError] from a
read once its service has stopped, where 0.17 returned the last value. Code
that polled a signal to learn whether the service still ran can catch that
error instead.

## A component's own `title` keyword needs another name

A view's [title](../explanation/glossary.md#title) is now the text the window
shows for it, so the session keeps the keyword `title` from the constructor,
as it keeps `placement`. It refuses a view whose constructor takes `title`,
and the session runs without that view. Rename the parameter:

```python
# 0.17
class MyView(QWidget):
    def __init__(self, name: str, parent: QWidget, title: str = "") -> None: ...


class MyApp(QtSession):
    my_view: Annotated[AsView[MyView], Declare(title="Commands")]


# 0.18
class MyView(QWidget):
    def __init__(self, name: str, parent: QWidget, caption: str = "") -> None: ...


class MyApp(QtSession):
    my_view: Annotated[AsView[MyView], Declare(caption="Commands")]
```

A session file that gives the keyword changes the same way, from `title:` to
`caption:` under the view's entry. To show the text on the view's dock or tab,
keep `title` in the declaration or the session file and remove the parameter
from the constructor.

Only a view takes `title`, so the session also refuses a presenter or a device
given `title` in its declaration or its session-file entry. Rename the
parameter of its constructor in the same way.
