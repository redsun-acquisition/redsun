# Container

::: redsun.containers.components
    show_root_heading: true
    options:
      members:
        - declare_device
        - declare_hook
        - declare_presenter
        - declare_view

::: redsun.containers.container.AppContainer
    options:
      show_root_heading: true


::: redsun.containers._config.AppConfig
    options:
      show_root_heading: true

::: redsun.containers.HookError
    options:
      show_root_heading: true

::: redsun._hooks.CreatesApplication
    options:
      show_root_heading: true

::: redsun._hooks.ConfiguresApplication
    options:
      show_root_heading: true

::: redsun._hooks.ConfiguresMainView
    options:
      show_root_heading: true

::: redsun._hooks.WrapsBuild
    options:
      show_root_heading: true

::: redsun.qt.QtAppContainer
    options:
      show_root_heading: true

::: redsun.containers.qt._hooks
    options:
      show_root_heading: true
      members:
        - QtCreatesApplication
        - QtConfiguresApplication
        - QtWrapsBuild
        - QtConfiguresMainView
