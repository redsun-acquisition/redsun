---
icon: lucide/circle-help
---

# How a component asks the session what it holds

Most of the time a component asks for one thing by its type: "give me the
`MotorReadings`". Sometimes it needs an answer instead: "which components in
this session can be reset?". The answer depends on what the session file puts
in the session, so no one can write it down in advance.

A component asks such a question in [`setup`](glossary.md#setup), with a
[protocol](glossary.md#protocol) that describes what it's looking for.

## Asking with an annotation

How you annotate the parameter says what you're asking for:

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
and nobody has to keep a list up to date.

[ADR 17](decisions/0017-questions-read-from-the-annotation.md) records why the
annotation carries the question.

## How a component matches

A component matches a protocol when it has every member the protocol lists,
and each of its methods accepts every call the protocol allows. This is
[structural subtyping](glossary.md#structural-subtyping): the component
doesn't have to inherit from the protocol, or even know it exists.

- An extra parameter **with** a default still matches.
- A renamed parameter, or an extra one without a default, doesn't.
- Types aren't compared, since that's a type checker's job.

The protocol doesn't need `runtime_checkable`, may list attributes as well as
methods, and may be generic: `Reading[float]` is matched as `Reading`.

When a component you expected is missing from an answer,
[`Session.satisfying`][redsun.Session.satisfying] shows the answer the session
gives, and [`Session.rejected`][redsun.Session.rejected] says why the
component isn't in it:

```python
>>> session.satisfying(Resettable)
{'motor': <Motor>, 'detector': <Detector>}
>>> session.rejected(Resettable)
{'loose': ["reset(hard) cannot be called as reset(): missing a required argument: 'hard'"]}
```

`rejected` lists only components that have some of the protocol's members, so
the near misses are easy to find.

## Asking for exactly one

A parameter annotated with the protocol alone asks for the one component, or
shared value, that satisfies it:

```python
class RoiView(QWidget):
    def setup(self, camera: HasCamera) -> None:
        self.camera = camera
```

If nothing matches, or more than one thing does, the session doesn't start,
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
depending on itself. It does appear in a `Mapping[str, P]` if it matches,
because that answer describes the whole session and is the same for everyone
who asks. When you need to, leave yourself out with one line:

```python
others = {name: c for name, c in self.resettable.items() if name != self.name}
```

If the only match failed to build, the session reports the asking component
as not set up, and runs without it.

## Asking about devices

Devices never answer a question in `setup`; only presenters, views and shared
values do. To ask which devices can do something, use
[`DevicesOf`][redsun.DevicesOf] in the constructor:

```python
class MotorPresenter:
    def __init__(self, name: str, *, motors: DevicesOf[Movable]) -> None:
        self.name = name
        self.motors = motors
```

The constructor can ask because devices exist before any presenter.
`DevicesOf` only works as `Mapping[str, P]` and only in a constructor. To get
every device, ask for [`DeviceMapping`][redsun.DeviceMapping].

## When not to ask

- To get one specific value, ask for it by its class instead.
- If components only need to hear when something happens, connect a signal
  to a slot in `wire` and skip the question.

!!! warning "A component can answer a question by accident"

    A component answers a question by what it has, whether it meant to or
    not, so any class with a `reset` method is `Resettable`. If that's not
    what you want, rename the method.
