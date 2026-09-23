# Questions

Most of the time a component asks for one thing by its type: "give me the
`MotorReadings`". Sometimes it needs an answer instead: "which components in
this session can be reset?". The answer depends on what the session file puts
in the session, so no one can write it down in advance.

A component asks such a question in `setup`, with a
[protocol](../reference/glossary.md#protocol) describing what it is looking
for.

## The shape of the parameter is the question

| annotation | what you get |
| --- | --- |
| `P` | the one component, or shared value, that satisfies `P` |
| `P \| None = None` | that one, or `None` if nothing does |
| `Mapping[str, P]` | every component satisfying `P`, by name |

```python
from collections.abc import Mapping
from typing import Protocol

from redsun import slot


class Resettable(Protocol):
    def reset(self) -> None: ...


class SessionPresenter:
    def __init__(self, name: str) -> None:
        self.name = name

    def setup(self, resettable: Mapping[str, Resettable]) -> None:
        self.resettable = resettable

    @slot
    def reset_all(self) -> None:
        for component in self.resettable.values():
            component.reset()
```

Whatever the session file puts in the session, `reset_all` resets all of it,
and nobody keeps a list up to date.

[ADR 17](decisions/0017-questions-read-from-the-annotation.md) records why the
annotation carries the question.

## How a component matches

A component matches a protocol when it has every member the protocol lists,
and each method accepts every call the protocol allows. This is
[structural subtyping](../reference/glossary.md#structural-subtyping): the
component does not have to inherit from the protocol, or even know it exists.

- An extra parameter **with** a default still matches.
- A renamed parameter, or an extra one without a default, does not.
- Types are not compared. That is a type checker's job.

The protocol does not need `runtime_checkable`, may list attributes as well as
methods, and may be generic: `Reading[float]` is matched as `Reading`.

When a component you expected is missing from an answer,
[`Session.rejected`][redsun.Session.rejected] says why:

```python
>>> session.rejected(Resettable)
{'loose': ["reset(hard) cannot be called as reset(): missing a required argument: 'hard'"]}
```

It lists only components that have some of the protocol's members, so the
near misses are easy to find.

## Asking for exactly one

```python
class RoiView(QWidget):
    def setup(self, camera: HasCamera) -> None:
        self.camera = camera
```

If nothing matches, or more than one thing does, the session does not start,
and the error names what came close:

```text
TypeError: 'roi' in its 'camera' parameter asks for the one object satisfying
'HasCamera', but 2 do, from 'camera', 'spare'. Narrow the protocol, or ask for
'Mapping[str, HasCamera]'.
```

Use `P | None = None` when the component can do without:

```python
def setup(self, roi: HasRoi | None = None) -> None:
    self.roi = roi
```

A component never answers its own single question, since that would mean
depending on itself. In a `Mapping[str, P]` it does appear if it matches: the
answer describes the whole session, the same for everyone who asks. Leave
yourself out with one line when you need to:

```python
others = {name: c for name, c in self.resettable.items() if name != self.name}
```

If the only match failed to build, the asking component is reported as not
set up, and the session runs without it.

## Asking about devices

A question in `setup` is answered by presenters, views and shared values,
never by devices. To ask which devices can do something, use
[`DevicesOf`][redsun.DevicesOf] in the constructor:

```python
class MotorPresenter:
    def __init__(self, name: str, *, motors: DevicesOf[Movable]) -> None:
        self.name = name
        self.motors = motors
```

Devices exist before any presenter, so the constructor can ask. `DevicesOf`
only works as `Mapping[str, P]` and only in a constructor. Ask for
[`DeviceMapping`][redsun.DeviceMapping] to get every device.

## When not to ask

- To get one specific value, ask for it by its class instead.
- If components only need to hear when something happens, connect a signal
  to a slot in `wire`, and skip the question.
- A component answers a question by what it has, whether it meant to or not.
  A class with a `reset` method is `Resettable`. Rename the method if that is
  not what you want.
