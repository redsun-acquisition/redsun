---
icon: lucide/flask-conical
---

# How to test a plugin

Test the components and services of a plugin with the fixtures `redsun` uses
for its own tests, from [`redsun.testing`](../reference/api/testing.md).

## Prerequisites

A plugin package with `pytest` tests. See
[Package components as a plugin](package-a-plugin.md). The blocks below are
parts of one test module; the whole module is at the end.

## Install the fixtures

Add `redsun` with the `testing` extra to the plugin's development
dependencies:

```bash
uv add --dev "redsun[testing]" pytest-asyncio
```

`pytest-asyncio` runs the `async` tests, such as the service test below.

## Load them

Load the module as a `pytest` plugin, in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "-p redsun.testing"
asyncio_mode = "auto"
```

From then on every test writes session log files under its own `tmp_path`,
and so do acquisition files and catalogs a session puts in their default
location, and every test drops the `psygnal` emissions it left queued for
another thread. A session whose configuration names its own `storage`
directory still writes there. The fixtures doing this run for each test, so
a session built in a fixture scoped to a module or the whole run is not
covered. Nothing loads the module unless a suite asks for it, so these
fixtures never reach a project that only installs `redsun`.

The module defines no `qapp` fixture. A session with a window needs a
`QApplication`: take the `qapp` fixture of `pytest-qt`, or define one.

## Build a session

Ask for [`build`][redsun.testing.build]. It builds a session class with the
configuration given, and shuts the session down when the test ends:

```{.python}
--8<-- "docs/examples/plugin_tests.py:build"
```

`mock: True` connects every device to a simulated backend, as in
[Run without hardware](run-without-hardware.md). It does not suit a device
whose signals come from its service when it connects, as a `fastcs` device's
do: mocked, it has none. Test such a device against its service instead.

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

The service is stopped when the test ends, its transport is released as
when a session ends, and the EPICS address list it added itself to is
restored, so the next test starts from the same list. The test reads the
prefix from the service it gets back.

Prefer `pv-access` for services started in tests. A Channel Access client
reads its address list once, the first time the process uses Channel Access,
so under `channel-access` a service started after that is not found. Start
every Channel Access service a suite needs before its first client connects.

## The example in full

??? example "The whole module"

    ```{.python}
    --8<-- "docs/examples/plugin_tests.py"
    ```
