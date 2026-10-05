# 21. A built-in light stack

Date: 2026-10-05

## Status

Accepted

## Context

Sessions that drive light sources need a presenter that switches and dims them
and a view with their controls. A plugin wrote both for its own devices, and
its device contract was a protocol listing four attribute names (`intensity`,
`wavelength`, `enabled`, `binary`) plus `trigger()` used as an on/off toggle.
In `bluesky`, `Triggerable` means "acquire", so a plan triggering such a light
would switch it. That view showed what had been asked for rather than what
the light reported, and wrote the intensity at every movement of the slider.

The positioner (ADR 20) already reads, follows and writes the configuration
of its devices, and shows it in a tab. A second stack doing the same would
otherwise copy that code.

## Decision

- `redsun` ships `LightPresenter` and `LightView`, under the plugin id
  `lights`.
- A light is a device whose `enabled` is a boolean signal it can write; a
  `DimmableLight` also has a numeric `intensity`. The presenter checks the
  signals' types, because matching a protocol by member names alone would
  take any device with an `enabled` attribute. No `trigger` toggle, no
  `binary` flag: a light without `intensity` is switched only.
- The wavelength and other details are configuration, shown in a tab.
- The view shows what each light reads back. The intensity is written when
  the slider is let go and on Enter, and optionally while dragging, at most
  every 100 ms; while a write is in progress, only the newest value asked for
  is written after it.
- Configuration code is shared, public, by composition:
  `DeviceConfiguration` on the presenter side and `ConfigurationTab` on the
  view side. The positioner uses both.

## Consequences

- A device offering the two signals under these names works with no other
  change; a device naming them otherwise needs a thin wrapper.
- Later stacks, built in or in a plugin, reuse `DeviceConfiguration` and
  `ConfigurationTab` rather than copying them.
- The plugin's light stack can be removed once its devices declare the
  wavelength as configuration and stop toggling on `trigger`.
