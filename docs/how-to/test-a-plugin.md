---
icon: lucide/flask-conical
---

# How to test a plugin

You can test the components and services of a plugin with the fixtures
`redsun` uses for its own tests, from
[`redsun.testing`](../reference/api/testing.md).

## Prerequisites

You need a plugin package with `pytest` tests, as
[Package components as a plugin](package-a-plugin.md) describes. The blocks
below are parts of one test module, and the whole module is at the end.

## Install the fixtures

Add `redsun` with the `testing` extra to the plugin's development
dependencies:

```bash
uv add --dev "redsun[testing]" pytest-asyncio
```

`pytest-asyncio` runs the `async` tests, such as the service test below.

## Load them

Load the module as a `pytest` plugin in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "-p redsun.testing"
asyncio_mode = "auto"
```

From then on every test keeps its session settings and session log files under
its own `tmp_path`. So do the acquisition files and catalogs a session puts in
their default location, and every test drops the `psygnal` emissions it left
queued for another thread. A session whose configuration names its own
`storage` directory still writes there. Nothing loads the module unless a suite
asks for it, so these fixtures never reach a project that only installs
`redsun`.

The fixtures also turn Python's automatic garbage collection off for the
whole run and collect once after each test file, because `pyside6` ends the
process when a widget is freed on a background thread. Three things follow
for your tests:

- A test that checks an object in a reference cycle was freed calls
  `gc.collect()` itself.
- A test that turns automatic collection on or off restores the state it
  found, or it fails with a message saying so:

    ```python
    found = gc.isenabled()
    gc.disable()
    try:
        ...
    finally:
        (gc.enable if found else gc.disable)()
    ```

- What a test leaves in a reference cycle, a widget or a large array, stays
  in memory until the end of its file.

[Garbage collection in the tests](contribute.md#garbage-collection-in-the-tests)
gives the reason.

!!! warning "A session built in a wider fixture isn't covered"

    The folder fixtures run for each test, so they don't cover a session built
    in a fixture scoped to a module or the whole run. Build the session in a
    per-test fixture.

The module defines no `qapp` fixture, and a session with a window needs a
`QApplication`. Take the `qapp` fixture of `pytest-qt`, or define one.

## Build a session

Ask for [`build`][redsun.testing.build]. It builds a session class with the
configuration you give it, and shuts the session down when the test ends:

```{.python}
--8<-- "docs/examples/plugin_tests.py:build"
```

`mock: True` connects every device to a simulated backend, as in
[Run without hardware](run-without-hardware.md). That doesn't suit a device
whose signals come from its service when it connects, as a `fastcs` device's
do, because a mocked one has none. Test such a device against its service
instead.

## Start a service

Declare the service once, with the [`Launch`][redsun.Launch] a session class
uses:

```{.python}
--8<-- "docs/examples/plugin_tests.py:declare"
```

Ask for [`start_service`][redsun.testing.start_service] and give it the name
the service is declared under, the `Launch`, and the transport the session
file names under `services.transport`:

```{.python}
--8<-- "docs/examples/plugin_tests.py:service"
```

When the test ends, the fixture stops the service, releases its transport as a
session does, and restores the EPICS address list the service added itself to,
so the next test starts from the same list. The test reads the prefix from the
service it gets back.

!!! warning "Channel Access services started late are not found"

    A Channel Access client reads its address list once, the first time the
    process uses Channel Access, so under `channel-access` a service started
    after that isn't found. Prefer `pv-access` for services started in tests, or
    start every Channel Access service the suite needs before its first client
    connects.

## The example in full

??? example "The whole module"

    ```{.python}
    --8<-- "docs/examples/plugin_tests.py"
    ```
