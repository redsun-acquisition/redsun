# Storage

## Writer

::: redsun.storage.Writer
    options:
      filters: ["!^__", "_on_prepare", "_write_frame", "_finalize"]

::: redsun.storage.FrameSink

## Path providers

::: redsun.storage.PathInfo
    options:
      show_root_heading: true
      show_docstring_parameters: false

::: redsun.storage.FilenameProvider
    options:
      show_root_heading: true
      filters: ["__call__"]

::: redsun.storage.PathProvider
    options:
      show_root_heading: true
      filters: ["__call__"]

::: redsun.storage.SessionPathProvider
    options:
      show_root_heading: true
      filters: ["__call__"]

## Metadata

::: redsun.storage.metadata

::: redsun.storage.register_metadata

::: redsun.storage.clear_metadata

## Factory & utilities

::: redsun.storage.PrepareInfo
    options:
      show_root_heading: true
      show_docstring_parameters: false

::: redsun.storage.device.make_writer
    options:
      show_root_heading: true

::: redsun.storage.presenter.get_available_writers
    options:
      show_root_heading: true

::: redsun.storage.utils.from_uri
    options:
      show_root_heading: true

## Protocols

::: redsun.storage.protocols
    options:
      members:
        - HasWriter
