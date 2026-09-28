---
icon: lucide/book-open
---

# Reference

Technical reference material: the API and the release notes.

### API

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
