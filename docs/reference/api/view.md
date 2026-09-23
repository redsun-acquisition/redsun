# View

## Placement

::: redsun.Placement
    options:
      show_root_heading: true

## Qt widgets

::: redsun.view.qt.utils
    options:
      members:
        - create_plan_widget
        - ActionButton
        - PlanInfoDialog

::: redsun.view.qt.utils.PlanWidget
    options:
      show_docstring_parameters: false

::: redsun.view.qt._widget_factory
    options:
      members:
        - create_param_widget
      filters: ["!^_"]

::: redsun.view.qt.treeview
    options:
      members:
        - DescriptorTreeView

## Built-ins

::: redsun.view.qt.builtins.LogView
