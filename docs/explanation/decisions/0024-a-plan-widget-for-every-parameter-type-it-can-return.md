# 24. A plan widget for every parameter type it can return

Date: 2026-10-06

## Status

Accepted

## Context

`create_plan_spec` refused a required parameter that no input could show, and
accepted any parameter with a default. The Qt view then built the inputs with
`magicgui`, and three kinds of parameter went wrong:

- an input that dropped its value, so the plan ran with another one: a list
  default came back empty, a fixed-length tuple came back as a list, and
  `None` came back as `0`;
- a parameter with a default and no input for its type, which made the view
  raise while it built the plan widget. Most `bluesky` plans take
  `md: dict[str, Any] | None = None`, so most of them could not be shown;
- `int | None` without a default, refused although an input could show it.

## Decision

- A parameter an input can show gets one that starts from its default and
  returns a value of the annotated type.
- A parameter no input can show is hidden when it has a default, and the plan
  keeps its default; without a default it is refused, as before. Refusing it
  always was rejected, since every plan taking `md` would be refused. Hiding
  only a parameter named `md` was rejected too, as a rule by name.
- Lists, sets, mappings, fixed-length tuples and unions get inputs built from
  the inputs of their parts, to any depth. A text field holding a Python
  literal was rejected, since users would type `{"x": [1.0]}` by hand. Plain
  Qt widgets were rejected, since the plan widget would read two kinds of
  input.
- `X | None` gets a "set" checkbox beside the input for `X`, and unticked
  sends `None`. Hiding it was rejected: the user could no longer set the
  value.
- A container annotation is accepted when the built-in its input returns
  satisfies its origin. A `dict` satisfies `MutableMapping[K, V]` and a
  `list` satisfies `Iterable[T]`, so both are accepted. `deque[T]` and
  `OrderedDict[K, V]` are not, since the plan would receive a `list` or a
  `dict`, not the class it names.
- A device can still be a parameter only as itself, a sequence or set of
  devices, or `*args`. A device inside the new shapes makes the parameter one
  no input can show.
- An input reports why its value is invalid, and the plan widget keeps Run
  disabled while any input does. The first reason shows as text under the
  parameters, as a light or an axis shows "failed: ...". Refusing the run
  after Run is pressed was rejected: the view does not let the value through
  in the first place.

### Before

```python
# untouched, the plan received positions=[], corner=[] and frames=0
def walk(
    positions: list[float] = [0.0, 1.0],
    corner: tuple[int, int] = (3, 4),
    frames: int | None = None,
) -> MsgGenerator[None]: ...


# building the plan widget raised
# ValueError: No widget found for type dict[str, typing.Any] ...
def scan(frames: int, md: dict[str, Any] | None = None) -> MsgGenerator[None]: ...


# building the plan widget raised
def amplify(gains: dict[str, list[float]] = {"x": [1.0]}) -> MsgGenerator[None]: ...


# bluesky.plans.count, with delay: float | Iterable[float] = 0.0:
# building the plan widget raised on delay
```

### After

```python
# untouched, the plan receives [0.0, 1.0], (3, 4) and None;
# ticking "set" beside frames sends the number
def walk(
    positions: list[float] = [0.0, 1.0],
    corner: tuple[int, int] = (3, 4),
    frames: int | None = None,
) -> MsgGenerator[None]: ...


# md is hidden, and the plan runs with md=None
def scan(frames: int, md: dict[str, Any] | None = None) -> MsgGenerator[None]: ...


# a table of keys whose values are lists; a repeated key keeps Run disabled,
# and widget.problems is ["gains: duplicate key: 'x'"]
def amplify(gains: dict[str, list[float]] = {"x": [1.0]}) -> MsgGenerator[None]: ...


# bluesky.plans.count: delay offers "float" or "list of float",
# and per_shot and md are hidden
```

## Consequences

- A plan accepted before still runs, now with the values the user sees. A
  plan whose parameter made the view raise now builds.
- A sequence parameter's input is a `SequenceEdit`, no longer `magicgui`'s
  `ListEdit`.
- `PlanWidget.problems` replaces the acquisition view's own check that a
  device was chosen, and Run no longer comes back enabled when a plan ends
  with no device chosen.
- A new shape of input needs a widget in `view/qt` and a matching rule in
  `create_plan_spec`. A test builds both for each annotation and fails when
  only one of them accepts it.
