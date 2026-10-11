# 31. Hook points take several providers and tolerate one that fails

Date: 2026-10-11

## Status

Accepted

Supersedes "one provider per point" of
[10. Toolkit hook points](0010-toolkit-hook-points.md) for the points whose
providers return nothing. The rest of that record stands: a
[hook](../glossary.md#hook) never changes what the session builds, and every
[hook point](../glossary.md#hook-point) belongs to a toolkit.

## Context

ADR 10 gave each hook point one provider and said there was no case for
more. The first style `redsun` shipped was that case. A style is a
`configure_application` provider, so a session that picked it could no
longer install a provider of its own at that point, to set the application's
icon for example.

Writing the style showed three more gaps:

- A provider that raised stopped the whole build. A style that could not
  write its icons kept an instrument from starting, while a component that
  fails to build is logged and skipped
  ([ADR 11](0011-tolerating-a-component-that-fails-to-build.md)).
- What a provider owes the session was written only in a how-to. The first
  design of the style left its changes on the application when the session
  shut down, and nothing but a review noticed.
- A session file could name a provider `redsun` ships by a short name, but a
  plugin's manifest could hold short names too, and they were silently
  ignored.

## Decision

- **A hook point takes one provider or several.** A session class says which
  in `hook_points`: a protocol alone means one provider, and the protocol
  wrapped in `Many` means any number. A point takes one when the session uses
  what the provider returns: `create_application` and `confirm_close`. The
  other points of `QtSession` take several.
- **Providers run in a fixed order:** those the class declares, in
  declaration order, then those the session file lists, in the order of the
  list. `Session.hooks` maps every point to a tuple in that order.
- **A provider that fails is skipped.** If it cannot be built, or its hook
  method raises, the session logs the error, drops the provider from every
  point it serves, lists it in the build summary and carries on. A skipped
  provider gets no `shutdown` call. `strict` turns a skipped provider into a
  failed build, as it does for a component.
- **Two points keep their own rule.** A `create_application` provider that
  cannot be built stops the build, because a session told which application
  to run on must not start on another. A `confirm_close` provider that raises
  is skipped, and the session decides by its own rule.
- **A provider undoes in `shutdown` what it changed** on the application or
  outside its window. The rule is on the reference page and in the
  protocols' docstrings, and `redsun.testing` fails a test that leaves the
  application's stylesheet, style or font changed.
- **Only `redsun` ships short names.** A plugin's manifest with a `hooks`
  section is invalid; a plugin's provider is named by its class path.

### Before

One provider at the point, so a style and an icon needed one class doing
both:

```python
class MyStyleAndIcon(NapariStyle):
    def configure_application(self, app: QApplication) -> None:
        super().configure_application(app)
        app.setWindowIcon(QIcon("lab.png"))


class MyApp(QtSession):
    configure_application: AsHook[MyStyleAndIcon]
```

A session file had no way to say it. And `session.hooks[point]` was one
provider:

```python
style = session.hooks[QtHook.CONFIGURE_APPLICATION]
```

### After

```python
class MyIcon:
    def configure_application(self, app: QApplication) -> None:
        app.setWindowIcon(QIcon("lab.png"))


class MyApp(QtSession):
    configure_application: AsHook[NapariStyle]
    icon: Annotated[AsHook[MyIcon], Serves(QtHook.CONFIGURE_APPLICATION)]
```

```yaml
hooks:
  configure_application:
    - napari
    - provider: "mylab.app:MyIcon"
```

```python
style, icon = session.hooks[QtHook.CONFIGURE_APPLICATION]
```

Other options were rejected:

- A style as a concept of its own, with a `style:` key in the session file
  and a build step. It would settle this case and make every later need a new
  key and a new step. With several providers at a point, a new need arrives
  as a provider.
- Keeping one provider per point and subclassing, as in "Before". A session
  file cannot do it.
- Skipping a `create_application` provider that failed, and running on the
  session's own application. The session would start as a different program
  without saying so.
- Letting plugins ship short names. Two plugins could ship the same name,
  and nobody has asked for it. It can be added later without breaking a file
  that is valid today.

## Consequences

- `Session.hooks` changed shape, which breaks code that read one provider
  from it.
- A frontend written before this record keeps working: its points are
  written as protocols alone, so each still takes one provider.
- A frontend calls a point with `Session.call_hooks`, which skips a provider
  that raises, or reads `Session.hooks` and reports a failure with
  `Session.skip_hook`.
- A provider that changed the application and then failed is not asked to
  undo it, since it gets no `shutdown` call. The log names the provider and
  the point, which is where to look.
- A settings dialog for a style needs no new mechanism: one provider can
  serve `configure_application` and `configure_main_view`, and add a menu
  entry at the second.
