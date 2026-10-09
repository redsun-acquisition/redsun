---
icon: lucide/code
---

# redsun.view

## Placement

::: redsun.Placement
    options:
      show_root_heading: true

## Keyboard shortcuts

::: redsun.shortcut
    options:
      show_root_heading: true

::: redsun.Shortcut
    options:
      show_root_heading: true

## Window layout

::: redsun.WindowLayout
    options:
      show_root_heading: true

::: redsun.Row
    options:
      show_root_heading: true

::: redsun.Column
    options:
      show_root_heading: true

::: redsun.Tabs
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
