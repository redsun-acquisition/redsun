---
icon: lucide/code
---

# redsun.view

## Placement

::: redsun.Placement
    options:
      show_root_heading: true

## Qt widgets

::: redsun.view.qt.utils
    options:
      members:
        - create_plan_widget
        - create_param_widget
        - ActionButton
        - PlanInfoDialog

::: redsun.view.qt.utils.PlanWidget
    options:
      show_root_heading: true
      show_docstring_parameters: false

::: redsun.view.qt.treeview
    options:
      members:
        - DescriptorTreeView
        - ConfigurationTab

### Parameter widgets

[`create_plan_widget`][redsun.view.qt.utils.create_plan_widget] gives each
parameter of a plan an input chosen by its annotation, starting from the
parameter's default. Device parameters go to the *Devices* group, the others
to *Parameters*. Each tab shows a signature and the inputs it gets.

=== "Numbers and text"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:values"
    ```

    ![Spin boxes for exposure and frames, and a text field for label](../images/parameters-values.png)

=== "Choices"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:choices"
    ```

    ![A combo box offering fast and slow, and one offering the binnings](../images/parameters-choices.png)

=== "Devices"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:devices"
    ```

    ![A Devices group with a box per readable device and a combo box for the motor, then a Parameters group with exposure and frames](../images/parameters-devices.png)

=== "Lists"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:lists"
    ```

    ![Three rows of positions, each with a remove button, and a button adding one](../images/parameters-lists.png)

=== "Optional"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:optional"
    ```

    ![An unticked set box beside a disabled spin box](../images/parameters-optional.png)

=== "Mapping"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:mapping"
    ```

    ![Two rows, each a key field and a value spin box, and a button adding one](../images/parameters-mapping.png)

=== "Union"

    ```{.python}
    --8<-- "docs/examples/parameter_widgets.py:union"
    ```

    ![A combo box choosing float or list of float above a spin box](../images/parameters-union.png)

A parameter no input can show, such as `md: dict[str, Any] | None = None`, is
left out, and the plan keeps its default. A repeated key or no device chosen
keeps Run disabled, and the first reason shows under the parameters. Which
annotations get an input is in
[How an annotation is read](presenter.md#how-an-annotation-is-read).

## Built-ins

::: redsun.view.qt.builtins.LogView
    options:
      show_root_heading: true

::: redsun.view.qt.builtins.AcquisitionView
    options:
      show_root_heading: true

::: redsun.view.qt.builtins.LightView
    options:
      show_root_heading: true

::: redsun.view.qt.builtins.LightGroup
    options:
      show_root_heading: true

::: redsun.view.qt.builtins.PositionerView
    options:
      show_root_heading: true

::: redsun.view.qt.builtins.PositionerGroup
    options:
      show_root_heading: true
