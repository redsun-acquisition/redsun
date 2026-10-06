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

    ![Spin boxes for exposure and frames, and a text field for label](images/parameters-values.png)

=== "Choices"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:choices"
    ```

    ![A combo box offering fast and slow, and one offering the binnings](images/parameters-choices.png)

=== "Devices"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:devices"
    ```

    ![A Devices group with a box per readable device and a combo box for the motor, then a Parameters group with exposure and frames](images/parameters-devices.png)

=== "Lists"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:lists"
    ```

    ![Three rows of positions, each with a remove button, and a button adding one](images/parameters-lists.png)

=== "Optional"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:optional"
    ```

    ![An unticked set box beside a disabled spin box](images/parameters-optional.png)

=== "Mapping"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:mapping"
    ```

    ![Two rows, each a key field and a value spin box, and a button adding one](images/parameters-mapping.png)

=== "Union"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:union"
    ```

    ![A combo box choosing float or list of float above a spin box](images/parameters-union.png)

Lists, sets, mappings, fixed-length tuples, optional values and unions nest:
a `dict[str, list[float]]` is a table whose values are lists. Every
annotation an input can show, and the shapes it cannot, are listed in
[How an annotation is read](../reference/api/presenter.md#how-an-annotation-is-read).

## Leave a parameter out

A parameter no input can show, such as `md: dict[str, Any] | None = None`, is
left out of the plan widget, and the plan keeps its default. Without a
default, `create_plan_spec` refuses the whole plan with
[`UnresolvableAnnotationError`][redsun.presenter.plan_spec.UnresolvableAnnotationError].

## See why Run is disabled

While an input holds a value the plan cannot take, such as a repeated mapping
key or no device chosen, Run stays disabled and the first reason shows under
the parameters.
[`PlanWidget.problems`][redsun.view.qt.utils.PlanWidget.problems] lists
every reason.
