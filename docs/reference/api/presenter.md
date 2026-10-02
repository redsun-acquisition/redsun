---
icon: lucide/code
---

# redsun.presenter

## Positioner

::: redsun.presenter.PositionerPresenter
    options:
      show_root_heading: true

::: redsun.presenter.AxisInfo
    options:
      show_root_heading: true

::: redsun.presenter.DescribesAxes
    options:
      show_root_heading: true

::: redsun.presenter.Axis
    options:
      show_root_heading: true

::: redsun.presenter.find_axes
    options:
      show_root_heading: true

## Plan specification

::: redsun.presenter.plan_spec
    options:
      members:
        - create_plan_spec
        - collect_arguments
        - resolve_arguments
        - ParamKind
        - UnresolvableAnnotationError

::: redsun.presenter.plan_spec.ParamDescription
    options:
      show_root_heading: true
      show_docstring_parameters: false

::: redsun.presenter.plan_spec.PlanSpec
    options:
      show_root_heading: true
      show_docstring_parameters: false

### How an annotation is read

Annotations map to `ParamDescription` fields, first match wins:

1. `Literal["a", "b"]` -> `choices=["a", "b"]`
2. `Sequence[MyDevice]` -> multi-select, `choices=<matching device names>`
3. `*args: MyDevice` (VAR_POSITIONAL) -> multi-select
4. `MyDevice` (bare protocol) -> single-select
5. Everything else -> a plain value, left to the view layer to render

Step 5 accepts:

- `int`, `float`, `str`, `bool`, `bytes` and `range`
- `Path`
- `datetime`, `date`, `time` and `timedelta`
- any `Enum` subclass
- a sequence of anything that is not a device

A required parameter with any other annotation raises
`UnresolvableAnnotationError`.

### From the values to a call

Once the user fills in the plan widget, the presenter turns the values into a
plan
call:

```python
from redsun.presenter.plan_spec import collect_arguments, resolve_arguments

# 1. Resolve: string device names -> live device instances
resolved = resolve_arguments(spec, widget_values, devices)

# 2. Collect: build (args, kwargs) matching the plan signature
args, kwargs = collect_arguments(spec, resolved)

# 3. Run
engine(my_plan(*args, **kwargs))
```

## Utilities

::: redsun.presenter.utils
    options:
      members:
        - get_choice_list
        - isdevice
        - isdevicesequence
        - isdeviceset
        - issequence
