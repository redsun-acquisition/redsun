---
icon: lucide/anchor
---

# Hook points

A [hook point](../explanation/glossary.md#hook-point) is a moment in the life
of a session at which it calls the providers installed there. This page lists
the points a [`QtSession`][redsun.qt.QtSession] calls, the order providers run
in, what happens when one fails, and what a provider owes the session.
[How to install hooks](../how-to/install-hooks.md) shows how to write and
install one.

## The points of a Qt session

| Point | Runs | Receives | Providers | Protocol |
| --- | --- | --- | --- | --- |
| `create_application` | first, and only when no `QApplication` exists yet | `argv` | one | [`CreatesApplication`][redsun.CreatesApplication] |
| `configure_application` | once the application and the colour scheme are set, before any view is made | the application | several | [`ConfiguresApplication`][redsun.ConfiguresApplication] |
| `during_build` | around the build steps | the application | several | [`WrapsBuild`][redsun.WrapsBuild] |
| `configure_main_view` | when the window is made, before it is shown | the main window | several | [`ConfiguresMainView`][redsun.ConfiguresMainView] |
| `confirm_close` | when the window is asked to close | nothing | one | [`ConfirmsClose`][redsun.ConfirmsClose] |

A plain [`Session`][redsun.Session] calls no hook point.

`create_application` and `confirm_close` take one provider because the
session uses what it returns: the application to run on, and whether to
close. The other points only tell their providers that something happened, so
any number can listen.

## Order

At a point that takes several providers, they run in this order:

1. the providers the session class declares, in the order it declares them,
   a base class's before its subclass's;
2. the providers the session file lists, in the order of the list.

A `during_build` provider returns a context manager that stays open for the
whole build. These are opened in that order and closed in the reverse order.

[`Session.hooks`][redsun.Session.hooks] maps every point to its providers in
run order, as a tuple, empty for a point with none.

## When a provider fails

A provider fails when its class cannot be imported or constructed, or when
its hook method raises.

| Where | What the session does |
| --- | --- |
| a point that takes several providers | logs the error, skips the provider at every point it serves, and lists it in the build summary as "Hooks skipped" |
| a `during_build` provider opening its context manager, told a build step, or closing it | the same, and still closes a context manager it opened |
| `create_application` | stops the build |
| `confirm_close` | logs the error, and decides by its own rule, as with no provider |

A skipped provider gets no `shutdown` call, so a change it made before it
failed stays. The log names the provider and the point it failed at.

A provider that serves `create_application` and another point, and cannot be
built, stops the build: the stricter rule of its points applies.

With `strict: true` in the session file, a skipped provider stops the build
at the `report` step, as a component that failed does.

A mistake in a declaration stops the build whatever `strict` says: a point
the session doesn't call, a short name `redsun` doesn't ship, a provider
without the point's method, or a second provider at a point that takes one.

## What a provider owes the session

- It undoes in `shutdown` what it changed. A stylesheet, a style, a font or a
  connection to a signal of the application outlives the session unless the
  provider takes it back. The session calls `shutdown` once per provider,
  the last built first.
- It does the work that can fail in the hook method. There the session catches
  the error and skips the provider. Work started later, in a slot or a timer,
  has no caller to report to.
- It keeps its state on itself. State on a module or a class is shared by
  every session in the process.

In a test run, [`keep_application_as_found`][redsun.testing.qt.keep_application_as_found]
fails a test that left the application's stylesheet, style, font or palette
changed, which is how a missing `shutdown` shows up.
