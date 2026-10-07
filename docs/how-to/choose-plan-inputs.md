---
icon: lucide/sliders-horizontal
---

# How to choose the inputs of a plan

A plan widget gives each parameter of a plan an input chosen by the
parameter's annotation, and the input starts from the parameter's default.
Pick the annotation for the input you want.

## Prerequisites

A plan a presenter offers, as in
[How to run a plan from a presenter](run-a-plan.md).

## Annotate each parameter

Device parameters go to the *Devices* group, the others to *Parameters*.
Each tab shows a signature and the inputs it gets.

=== "Numbers and text"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:values"
    ```

    <figure markdown="span">
      ![Spin boxes for exposure and frames, and a text field for label](images/parameters-values-light.png#only-light)
      ![Spin boxes for exposure and frames, and a text field for label](images/parameters-values-dark.png#only-dark)
    </figure>

=== "Choices"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:choices"
    ```

    <figure markdown="span">
      ![A combo box offering fast and slow, and one offering the binnings](images/parameters-choices-light.png#only-light)
      ![A combo box offering fast and slow, and one offering the binnings](images/parameters-choices-dark.png#only-dark)
    </figure>

=== "Devices"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:devices"
    ```

    <figure markdown="span">
      ![A Devices group with a box per readable device and a combo box for the motor, then a Parameters group with exposure and frames](images/parameters-devices-light.png#only-light)
      ![A Devices group with a box per readable device and a combo box for the motor, then a Parameters group with exposure and frames](images/parameters-devices-dark.png#only-dark)
    </figure>

=== "Lists"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:lists"
    ```

    <figure markdown="span">
      ![Three rows of positions, each with a remove button, and a button adding one](images/parameters-lists-light.png#only-light)
      ![Three rows of positions, each with a remove button, and a button adding one](images/parameters-lists-dark.png#only-dark)
    </figure>

=== "Optional"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:optional"
    ```

    <figure markdown="span">
      ![An unticked set box beside a disabled spin box](images/parameters-optional-light.png#only-light)
      ![An unticked set box beside a disabled spin box](images/parameters-optional-dark.png#only-dark)
    </figure>

=== "Mapping"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:mapping"
    ```

    <figure markdown="span">
      ![Two rows, each a key field and a value spin box, and a button adding one](images/parameters-mapping-light.png#only-light)
      ![Two rows, each a key field and a value spin box, and a button adding one](images/parameters-mapping-dark.png#only-dark)
    </figure>

=== "Union"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:union"
    ```

    <figure markdown="span">
      ![A combo box choosing float or list of float above a spin box](images/parameters-union-light.png#only-light)
      ![A combo box choosing float or list of float above a spin box](images/parameters-union-dark.png#only-dark)
    </figure>

Lists, sets, mappings, fixed-length tuples, optional values and unions nest:
a `dict[str, list[float]]` is a table whose values are lists. Every
annotation an input can show, and the shapes it cannot, are listed in
[How an annotation is read](../reference/api/presenter.md#how-an-annotation-is-read).

## Limit the values a parameter takes

Most plan parameters only make sense in a range. A camera cannot expose for
0 seconds, and a scan needs at least one frame. Without limits, the plan
widget accepts any number. A wrong value is then found only when the plan
runs: the plan raises, or a device refuses the value partway through.

Write the limits in the plan's signature instead, with
[`annotated-types`](https://github.com/annotated-types/annotated-types). The
plan widget stops each input at its limits, and shows why Run is disabled
while a value is outside them. The presenter checks the same limits, so a
plan started from code gets the same protection:

```{.python}
--8<-- "docs/examples/parameter_widgets.py:limits"
```

<figure markdown="span">
  ![A spin box for frames, a spin box for exposure with three decimals, and two rows of points](images/parameters-limits-light.png#only-light)
  ![A spin box for frames, a spin box for exposure with three decimals, and two rows of points](images/parameters-limits-dark.png#only-dark)
</figure>

| Limit | What the input does |
| --- | --- |
| `Ge`, `Le`, `Interval` | the spin box stops at the bound |
| `Gt`, `Lt` | for an `int`, the spin box stops one past the bound; for a `float`, at the bound, and the bound itself is a problem |
| `MultipleOf` | the spin box steps by it and shows as many decimals as it needs |
| `MaxLen`, `Len` | a list or a mapping stops adding rows at the maximum |
| `MinLen`, a text too long | a problem |

The limits work inside other types too: `list[Annotated[float, Ge(0)]]`
limits every item. A number with no limit can take any value.

A plan whose default breaks its own limits is left out when the session
builds, and the log says which limit it breaks.

A `magicgui` option dict in the annotation still shapes the input, for
example `{"widget_type": "Slider"}`. Where it gives a bound that a limit also
gives, the limit wins.

## Leave a parameter out

A parameter no input can show, such as `md: dict[str, Any] | None = None`, is
left out of the plan widget, and the plan keeps its default. Without a
default, `create_plan_spec` refuses the whole plan with
[`UnresolvableAnnotationError`][redsun.presenter.plan_spec.UnresolvableAnnotationError].

## See why Run is disabled

While an input holds a value the plan cannot take, such as a repeated mapping
key, a value outside its limits or no device chosen, Run stays disabled and the first reason shows under
the parameters.
[`PlanWidget.problems`][redsun.view.qt.utils.PlanWidget.problems] lists
every reason.
