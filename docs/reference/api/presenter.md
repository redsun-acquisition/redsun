---
icon: lucide/code
---

# redsun.presenter

## Positioner

::: redsun.presenter.PositionerPresenter
    options:
      show_root_heading: true

::: redsun.presenter.DescribesAxes
    options:
      show_root_heading: true

## Acquisition

::: redsun.presenter.AcquisitionPresenter
    options:
      show_root_heading: true

::: redsun.presenter.DescribesPlans
    options:
      show_root_heading: true

## Lights

::: redsun.presenter.LightPresenter
    options:
      show_root_heading: true

::: redsun.presenter.DescribesLights
    options:
      show_root_heading: true

## Shared parts

::: redsun.presenter.DeviceConfiguration
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

Step 5 accepts an annotation an input can show:

| Annotation | Shown when |
| --- | --- |
| `int`, `float`, `str`, `bool`, `bytes`, `range`, `Path`, `datetime`, `date`, `time`, `timedelta`, an `Enum`, a `Literal` | always |
| `list[T]`, `Sequence[T]`, `Iterable[T]`, `tuple[T, ...]`, `set[T]`, `frozenset[T]`, or any one-element container a `list`, `tuple`, `set` or `frozenset` satisfies | `T` can be shown |
| `tuple[A, B]` of fixed length | every member can be shown |
| `dict[K, V]`, `Mapping[K, V]`, or any mapping a `dict` satisfies | `K` is a plain type, an `Enum` or a `Literal`, and `V` can be shown |
| `X \| None` | `X` can be shown |
| `A \| B` | every member can be shown |

`Annotated` metadata is set aside when deciding, at every level, so
`list[Annotated[float, ...]]` is read as `list[float]`. A device inside any of these shapes cannot be shown, and neither can `Any`, a
`Callable`, a container without type arguments, or a container no built-in
satisfies, such as `deque[T]` or `OrderedDict[K, V]`: the plan would receive
a `list` or a `dict`, not the class it names.

`annotated-types` limits in the metadata are kept in
`ParamDescription.annotated` and checked by `ParamDescription.problems`; see
[Limit the values a parameter takes](../../how-to/choose-plan-inputs.md#limit-the-values-a-parameter-takes).

| Parameter | Outcome |
| --- | --- |
| an input can show it | an input, starting from the default |
| no input can show it, and it has a default | `hidden=True`: a view leaves it out and the plan keeps its default |
| no input can show it, and it has no default | `UnresolvableAnnotationError` |

The inputs each annotation gets are pictured in
[How to choose the inputs of a plan](../../how-to/choose-plan-inputs.md).

### From the values to a call

Once the user fills in the plan widget, the presenter turns the values into a
plan
call:

```python
from redsun.presenter.plan_spec import collect_arguments, resolve_arguments

# 1. Resolve: string device names -> live device instances, hidden parameters -> their defaults
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
        - device_class
        - get_choice_list
        - isdevice
        - isdevicesequence
        - isdeviceset
        - issequence
