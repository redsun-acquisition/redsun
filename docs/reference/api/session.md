---
icon: lucide/code
---

# redsun.session

## The session

::: redsun.Session
    options:
      show_root_heading: true
      filters: ["!^_", "!^(read_configuration|start_runtime|start_services|build_devices|connect_built_devices|open_registry|build_presenters|build_views|setup_components|seal|apply_wiring|present|log_summary)$"]

### Build steps

`build` runs these methods of `Session` in this order. A subclass replaces one
by overriding it.

::: redsun.Session.read_configuration
    options:
      show_root_heading: true
      heading_level: 4

::: redsun.Session.start_runtime
    options:
      show_root_heading: true
      heading_level: 4

::: redsun.Session.start_services
    options:
      show_root_heading: true
      heading_level: 4

::: redsun.Session.build_devices
    options:
      show_root_heading: true
      heading_level: 4

::: redsun.Session.connect_built_devices
    options:
      show_root_heading: true
      heading_level: 4

::: redsun.Session.open_registry
    options:
      show_root_heading: true
      heading_level: 4

::: redsun.Session.build_presenters
    options:
      show_root_heading: true
      heading_level: 4

::: redsun.Session.build_views
    options:
      show_root_heading: true
      heading_level: 4

::: redsun.Session.setup_components
    options:
      show_root_heading: true
      heading_level: 4

::: redsun.Session.seal
    options:
      show_root_heading: true
      heading_level: 4

::: redsun.Session.apply_wiring
    options:
      show_root_heading: true
      heading_level: 4

::: redsun.Session.present
    options:
      show_root_heading: true
      heading_level: 4

::: redsun.Session.log_summary
    options:
      show_root_heading: true
      heading_level: 4

::: redsun.BuildableSession
    options:
      show_root_heading: true
      members: false

[`BuildableSession`][redsun.BuildableSession] lists the same methods; they
are described above, with [`Session`][redsun.Session].

::: redsun.DesktopSession
    options:
      show_root_heading: true

## Declaring components

::: redsun.AsDevice
    options:
      show_root_heading: true

::: redsun.AsPresenter
    options:
      show_root_heading: true

::: redsun.AsView
    options:
      show_root_heading: true

::: redsun.AsService
    options:
      show_root_heading: true

::: redsun.AsHook
    options:
      show_root_heading: true

::: redsun.Declare
    options:
      show_root_heading: true

::: redsun.FromConfig
    options:
      show_root_heading: true

::: redsun.Alias
    options:
      show_root_heading: true

::: redsun.Launch
    options:
      show_root_heading: true

::: redsun.Attach
    options:
      show_root_heading: true

::: redsun.Serves
    options:
      show_root_heading: true

::: redsun.Layer
    options:
      show_root_heading: true

::: redsun.session.Declaration
    options:
      show_root_heading: true

## What a component is held to

::: redsun.NamedComponent
    options:
      show_root_heading: true

::: redsun.AttachableComponent
    options:
      show_root_heading: true

::: redsun.HasSetup
    options:
      show_root_heading: true

::: redsun.HasShutdown
    options:
      show_root_heading: true

::: redsun.HasAsyncShutdown
    options:
      show_root_heading: true

::: redsun.Serializable
    options:
      show_root_heading: true

## Hook points

The protocol of each hook point, in the order a session reaches them.

::: redsun.CreatesApplication
    options:
      show_root_heading: true

::: redsun.ConfiguresApplication
    options:
      show_root_heading: true

::: redsun.WrapsBuild
    options:
      show_root_heading: true

::: redsun.ConfiguresMainView
    options:
      show_root_heading: true

::: redsun.ConfirmsClose
    options:
      show_root_heading: true

## Frontends and placements

::: redsun.Frontend
    options:
      show_root_heading: true

[`Placement`][redsun.Placement] is described with
[`redsun.view`](view.md#placement).

## Settings

::: redsun.Settings
    options:
      show_root_heading: true

## Errors

The exceptions a session raises are in [`redsun.errors`](errors.md).

## Build steps

::: redsun.session.BUILD_STEPS
    options:
      show_root_heading: true
