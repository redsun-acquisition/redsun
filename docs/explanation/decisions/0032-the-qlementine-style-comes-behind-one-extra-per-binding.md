# 32. The qlementine style comes behind one extra per Qt binding

Date: 2026-10-12

## Status

Accepted

## Context

`redsun` ships the `napari` style whole, because it is a stylesheet and a
set of pictures ([ADR 30](0030-napari-styling-is-copied-until-napari-publishes-it.md)).
`qlementine` is a compiled Qt style, published as one package per Qt
binding: `PyQt6-Qlementine` and `PySide6-Qlementine`. Three facts about
those packages shaped how a session gets the style:

- Nothing tells an installer which Qt binding a project uses, so one extra
  cannot pick the right package.
- `PySide6-Qlementine` accepts one version of `pyside6`, 6.10.2, and needs
  the whole `pyside6`, where `redsun` installs `pyside6-essentials`.
- The style changes more than a stylesheet does: it replaces the
  application's style, font and palette.

## Decision

- **One extra per binding:** `qlementine-pyqt` and `qlementine-pyside`.
  Each brings the window's own requirements, so it is the only extra a
  session with this style names.
- **The package is imported when the hook runs.** A session that does not
  name the style never imports it. A session that names it without the
  package logs which extra to install and starts unstyled, as any hook
  provider that fails does
  ([ADR 31](0031-hook-points-take-several-providers.md)).
- **`redsun`'s own lock holds two versions of `pyside6`.** A `conflicts`
  entry of `uv` says the `pyside` and `qlementine-pyside` environments are
  never installed together, so every other environment stays on the newest
  `pyside6`, and the style's tests run in an environment of their own.
- **`qlementine` colours the icons.** Its palette gives `ButtonText` the
  colour of the text on its accent buttons, so an icon drawn in the
  palette's colour, as the `napari` style has it, vanishes on every other
  button. The style turns on `qlementine`'s own icon colouring, which draws
  each icon in the colour of the control it is on.
- **`shutdown` puts back the style, the font and the palette.** A style the
  application held without a name cannot be put back.

```toml
[project.optional-dependencies]
qlementine-pyqt = ["redsun[pyqt]", "pyqt6-qlementine>=1.5.1"]
qlementine-pyside = ["redsun[qt-common]", "pyside6-qlementine>=1.5.1"]
```

```yaml
hooks:
  configure_application: qlementine
```

Other options were rejected:

- One `qlementine` extra holding both packages. It would install both Qt
  bindings.

    ```toml
    qlementine = ["pyqt6-qlementine>=1.5.1", "pyside6-qlementine>=1.5.1"]
    ```

- No extra, and a line in the guide telling the user which package to
  install. The requirement would be written nowhere a tool reads.
- One extra for `pyqt6` only, until the `pyside6` package accepts newer
  versions. A `pyside6` session would have no supported way to the style.
- Holding every `pyside6` environment at 6.10.2. The suite would stop
  testing the versions most users install.

## Consequences

- A `pyside6` session with this style runs on `pyside6` 6.10.2 until
  `PySide6-Qlementine` accepts more. The extra moves with it.
- `PyQt6-Qlementine` is GPL-3.0-only. The `pyqt` extra already installs
  GPL software, so `qlementine-pyqt` adds no new condition.
- The packages exist for Windows on x64, macOS on Apple silicon and Linux
  on x64. On another platform the extra does not install.
- qlementine animates a change of colour, so a control shows its old colour
  for a moment after the theme changes. A test reads the application's
  palette, which changes at once.
