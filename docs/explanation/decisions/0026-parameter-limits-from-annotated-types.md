# 26. Parameter limits from `annotated-types`, checked by `pydantic`

Date: 2026-10-07

## Status

Accepted

## Context

A plan author had no way to say that a parameter takes at least 1, or at
most 10. The plan widget also got some ranges wrong on its own: every number
without options was held between 0 and 999, so a negative value could not be
typed. `magicgui` 0.10.2 reads only the first item of an `Annotated`
annotation, and only when it is a dict, so limits written with
`annotated-types` never reached a widget. The presenter checked no values
before a launch.

## Decision

- Limits are written with `annotated-types`: `Ge`, `Le`, `Gt`, `Lt`,
  `Interval`, `MultipleOf`, `MinLen`, `MaxLen` and `Len`, at any level of the
  annotation.
- `pydantic` checks them. A parameter with a limit gets one strict
  `TypeAdapter`, built when the plan is read. Its errors become problem
  lines, located inside the value: `points[2]: Input should be greater than
  or equal to 0`. Building takes well under a millisecond and a check a few
  microseconds.
- The view and the presenter use the same check. The view shows the lines and
  keeps Run disabled; the presenter refuses a launch with them.
- A default that breaks its own limits leaves the plan out.
- A limit wins over a `magicgui` option dict that gives the same bound.
- Until `magicgui` reads `annotated-types` itself, the view turns the limits
  into `min`, `max` and `step` options.
- A number without a limit has no range limit.

Rejected: our own check walking each shape (about a hundred lines repeating
what `pydantic` does); the tighter of a dict and a limit (the input would
refuse values the presenter accepts); accepting or clamping a broken default
(the author's mistake would reach every user, or change without a word).

### Before

```python
def expose(frames: int = 1, exposure: float = 0.1) -> MsgGenerator[None]:
    if frames < 1 or not 0 < exposure <= 10:
        raise ValueError("frames >= 1 and 0 < exposure <= 10")
    ...
```

The plan widget offers 0 frames and any exposure from 0 to 999, and the user
learns about the limits only when the plan fails.

### After

```python
def expose(
    frames: Annotated[int, Ge(1)] = 1,
    exposure: Annotated[float, Gt(0), Le(10)] = 0.1,
) -> MsgGenerator[None]: ...
```

The spin boxes stop at the limits, an exposure of 0 shows a problem and keeps
Run disabled, and the presenter refuses the same values from code.

## Consequences

- A plan states its limits once, in its signature, and every way of running
  it respects them.
- `ParamDescription` gains `annotated` and `problems`.
- `create_plan_spec` and `resolve_arguments` raise `ValueError` for a value
  outside its limits.
- `pydantic` becomes part of how plans are read, beside how session files are
  read.
- The view's translation of limits into `magicgui` options goes once a
  `magicgui` release reads `annotated-types`.
