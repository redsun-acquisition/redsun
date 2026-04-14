# Storage

## Writer

::: redsun.storage.Writer
    options:
      filters: ["!^__", "!^_"]

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

## Protocols

::: redsun.storage.HasWriterLogic

::: redsun.storage.HasMetadata

## Metadata callback

::: redsun.storage.handle_descriptor_metadata

## Presenter utilities

::: redsun.storage.presenter.get_available_writers
    options:
      show_root_heading: true

::: redsun.storage.utils.from_uri
    options:
      show_root_heading: true
