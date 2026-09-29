---
icon: lucide/book-open
---

# Reference

Technical reference material: the glossary, the files a session reads, the
variables it sets, the API and the release notes.

### Glossary

- [Glossary](../explanation/glossary.md): the words the documentation uses,
  each defined once

### Files

- [Session file](session-file.md): every key of a session file
- [Plugin manifest](plugin-manifest.md): every key of the manifest of a
  plugin

### Environment

- [Environment variables](environment.md): what a session sets for its
  services and for itself, and what it reads

### API by task

| To | Look up |
| --- | --- |
| declare the components of a session | [Declaring components](api/session.md#declaring-components) |
| check what a component must have | [What a component is held to](api/session.md#what-a-component-is-held-to) |
| act at a moment of the build | [Hook points](api/session.md#hook-points) |
| change one step of the build | [Build steps](api/session.md#build-steps) |
| share a value, or ask the session for one | [`redsun.injection`](api/injection.md), [`redsun.registry`](api/registry.md) |
| connect a signal to a slot | [`redsun.ports`](api/ports.md) |
| describe a plan and build its controls | [`redsun.presenter`](api/presenter.md), [Qt widgets](api/view.md#qt-widgets) |
| run a plan, or one that runs until stopped | [`redsun.engine`](api/engine.md) |
| place a view in the window | [Placements](api/qt.md#placements) |
| keep a setting between runs | [Settings](api/session.md#settings) |
| choose where files go | [`redsun.path_provider`](api/path_provider.md) |
| launch or attach to a service | [`redsun.services`](api/services.md) |
| log from a component | [`redsun.log`](api/log.md) |
| catch what a session raises | [`redsun.errors`](api/errors.md) |

### API by module

Look up a class or a function by the module it is imported from.

- `redsun`: everything a component or a session imports
    - [`redsun.aio`](api/aio.md): run a coroutine on the event loop the
      session shares
    - [`redsun.catalog`](api/catalog.md): the catalog of runs a session keeps
    - [`redsun.engine`](api/engine.md): the `RunEngine` that runs the plans of
      a presenter
        - [`redsun.engine.actions`](api/engine.md#actions): plans that run
          until stopped, and the actions a user takes while they run
        - [`redsun.engine.plan_stubs`](api/engine.md#plan-stubs): steps a
          plan uses to wait for an action
    - [`redsun.errors`](api/errors.md): the exceptions a session raises
    - [`redsun.injection`](api/injection.md): how a component says what it
      needs and what it offers
    - [`redsun.log`](api/log.md): the logger, and the records of a session
    - [`redsun.path_provider`](api/path_provider.md): where the acquisition
      files of a session go
    - [`redsun.ports`](api/ports.md): slots, and the connections a session
      makes
    - [`redsun.presenter`](api/presenter.md): descriptions of plans, for the
      widgets that show them
        - [`redsun.presenter.plan_spec`](api/presenter.md#plan-specification):
          the description of a plan's parameters
        - [`redsun.presenter.utils`](api/presenter.md#utilities): helpers
          that inspect those parameters
    - [`redsun.qt`](api/qt.md): the Qt session, its placements and its menus
    - [`redsun.registry`](api/registry.md): the values every component may
      ask for
    - [`redsun.services`](api/services.md): the servers devices talk to
    - [`redsun.session`](api/session.md): the session, and how components
      are declared
    - [`redsun.utils`](api/utils.md): general helpers
        - [`redsun.utils.descriptors`](api/utils.md): reading the keys of
          `bluesky` descriptors and readings
    - [`redsun.view`](api/view.md): where a view asks to be shown
        - [`redsun.view.qt`](api/view.md#qt-widgets): Qt widgets views share
    - [`redsun.writers`](api/writers.md): writing a derived product

<!-- ends the list above, so the two below are a list of their own -->

- [Changelog](changelog.md)
- [Previous changelog](previous-changelog.md)
